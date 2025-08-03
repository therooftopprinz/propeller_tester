#include <HX711.h>

// Pin Definitions
#define HX711_DT 4
#define HX711_SCK 5
#define ESC_PWM 9
#define TACHO 2
#define CURRENT_SENSOR A7
#define VOLTAGE_SENSOR A0

// Config
const float MV_PER_AMP   = 39.8; // 100mV/A for STK-600/M 50A model
const float VCC          = 5.0;  // VCC
const int ADC_RESOLUTION = 1024; // 10-bit ADC
double VOLT_PER_TICK = 0.04881;
int N_BLADE = 2;

template <unsigned N, typename T = float >
class average_window
{
public:
    average_window()
    {
        for (unsigned i = 0; i<N; i++)
        {
            samples[i] = 0;
        }
    }

    void add(T n)
    {
        samples[idx] = n;
        idx++;
        if (idx>=N)
        {
            idx = 0;
        }
    }

    T value()
    {
        T sum = 0;
        for (int i=0; i<N; i++)
        {
            sum += samples[i];
        }
        return sum/N;
    }
private:
    T samples[N];
    unsigned idx = 0;
};

struct schedule_context
{
    unsigned long last = 0;
    unsigned long interval = 100;
    unsigned long diff = 0;
    operator bool()
    {
        unsigned long now = millis();
        if (now - last >= interval)
        {
            diff = now - last;
            last = now;
            return true;
        }
        return false;
    }
};

struct LoadCell
{
    void begin(int dt, int ck, int scale)
    {
        device.begin(dt, ck);
        device.set_scale(scale);
    }
    
    void schedule()
    {
        if (scheduler)
        {
            sampler.add(device.get_units(1));
        }
    }

    HX711 device;
    schedule_context scheduler;
    average_window<3> sampler;
};

template <int tag>
struct TachoMeter
{
public:
    void begin(int pin)
    {
        pinMode(pin, INPUT_PULLUP);
        attachInterrupt(digitalPinToInterrupt(pin), TachoMeter<tag>::isr, FALLING);    
    }

    void schedule()
    {
        if (scheduler)
        {
            float rpm = 60 * count * (1000.0 / scheduler.diff);
            count = 0;
            sampler.add(rpm);
        }
    }

    schedule_context scheduler;
    average_window<10> sampler;

    static unsigned int count;
    static unsigned int acount;
    static unsigned long last;
    static void isr()
    {
        unsigned long now = millis();
        if ((now-last)<=2)
          return;
        count++;
        acount++;
        last = now;
    }
};

class TachoMeter2
{
public:
    void begin(int pinx)
    {
        pin = pinx;
        pinMode(pinx, INPUT_PULLUP);

        state = 0;

        pin_scheduler.interval = 1;
    }

    void schedule()
    {
        if (pin_scheduler)
        {
            int v = digitalRead(pin);
            pin_sampler.add(v);
            float av = pin_sampler.value();
            if (av>=0.9)
            {
                if (!state)
                {
                    count++;
                    acount++;
                    state = 1;
                }
            }
            else
            {
                state = 0;
            }
        }
        if (scheduler)
        {
            float rpm = 60 * count * (1000.0 / scheduler.diff);
            count = 0;
            sampler.add(rpm);
        }
    }

    schedule_context  pin_scheduler;
    average_window<3> pin_sampler;

    schedule_context   scheduler;
    average_window<10> sampler;

    int state;

    int count;
    int acount;
    int pin;
};

class ServoTimer1
{
public:
    void begin(int pin)
    {
        pinMode(pin, OUTPUT);

        TCCR1A = 0;
        TCCR1B = 0;

        // Set phase-correct PWM with ICR1 as TOP (Mode 10)
        TCCR1A |= (1 << COM1A1) | (1 << WGM11); // Non-inverting mode
        TCCR1B |= (1 << WGM13) | (1 << CS11);   // Prescaler = 8, Mode 10

        // Set frequency to 50Hz (period = 20ms)
        ICR1 = 20000; // TOP value = (16e6 Hz) / (8 prescaler * 50 Hz * 2) = 20000

        // Initial pulse width
        OCR1A = 1000;
    }

    void setPulseWidth(uint16_t pulseWidth)
    {
        pulseWidth = constrain(pulseWidth, 1000, 2000);
        OCR1A = pulseWidth;
    }
};

class CurrentSensor
{
public:
    void begin(int pin_)
    {
        pin = pin_;
        callibrate();
    }

    void callibrate()
    {
        float sum = 0;
        for (int i = 0; i < 100; i++) {
            sum += analogRead(pin);
            delay(1);
        }
        currentOffset = (sum / 100.0) * (VCC / ADC_RESOLUTION);
    }

    void schedule()
    {
        if (scheduler)
        {
            float voltage = analogRead(pin) * (VCC / ADC_RESOLUTION);
            sampler.add((voltage - currentOffset) / (MV_PER_AMP / 1000.0));
        }
    }

    schedule_context scheduler;
    average_window<10> sampler;

private:
    int pin;
    float currentOffset;
};

class VoltageSensor
{
public:
    void begin(int pin_)
    {
        pin = pin_;
    }

    void schedule()
    {
        if (scheduler)
        {
            sampler.add(analogRead(pin) * VOLT_PER_TICK);
        }
    }

    schedule_context scheduler;
    average_window<10> sampler;

private:

    int pin;
};

LoadCell Thrust;
TachoMeter<0> RPM;
template<> unsigned int TachoMeter<0>::count = 0;
template<> unsigned int TachoMeter<0>::acount = 0;
template<> unsigned long TachoMeter<0>::last = 0;
//TachoMeter2 RPM;

ServoTimer1 Motor;
CurrentSensor Current;
VoltageSensor Voltage;

// Output
schedule_context CSVLogSchedule;

// Low V Prot
float VoltageThreshold = 9999;

void setup()
{
    Serial.begin(115200);
    Thrust.begin(HX711_DT, HX711_SCK, 360);
    RPM.begin(TACHO);
    Motor.begin(ESC_PWM);
    Current.begin(CURRENT_SENSOR);
    Voltage.begin(VOLTAGE_SENSOR);

    CSVLogSchedule.interval = 200;

    Serial.println("Ready!");
    Serial.println("Format: time(ms),load(g),current(A),voltage(V),angspeed(RPM)");
}

void clearRx()
{
    while (Serial.available() && Serial.read() != '\n');
}

unsigned int lcx = 0;
void loop() {
    if (Serial.available() > 0)
    {
        char c = Serial.read();
        if ('A' == c)
        {
            Current.callibrate();
            Serial.println("Cal A");
            clearRx();
            return;
        }
        if ('T' == c)
        {
            Thrust.device.tare(10);
            Serial.println("Tare");
            clearRx();
            return;
        }
        if ('S' == c) 
        {
            float scale = Serial.parseFloat();
            Thrust.device.set_scale(scale);
            Serial.println("Scale");
            clearRx();
            return;
        }
        if ('N' == c)
        {
            int N_BLADE = Serial.parseInt();
            if (N_BLADE == 0) N_BLADE = 2;
            Serial.println("Blade");
            clearRx();
            return;
        }
        if ('V' == c)
        {
          double v0 = Serial.parseFloat();
          float v = Voltage.sampler.value();
          VOLT_PER_TICK *= (v0/v);
          Serial.println("Volt");
        }
        if ('L' == c)
        {
            VoltageThreshold = Serial.parseFloat();
            Serial.println("Low");
        }

        int pulseWidth = Serial.parseInt();
        Motor.setPulseWidth(pulseWidth);
        Serial.print("P");
        Serial.println(pulseWidth);
        clearRx();
    }

    Thrust.schedule();
    RPM.schedule();
    Current.schedule();
    Voltage.schedule();

    if (VoltageThreshold >= Voltage.sampler.value())
    {
        Motor.setPulseWidth(0);
        VoltageThreshold = 9999;
    }

    if (CSVLogSchedule)
    {
        Serial.print(CSVLogSchedule.last);
        Serial.print(",");
        Serial.print(Thrust.sampler.value(), 1);
        Serial.print(",");
        Serial.print(Current.sampler.value(), 3);
        Serial.print(",");
        Serial.print(Voltage.sampler.value(), 3);
        Serial.print(",");
        Serial.print(RPM.sampler.value()/N_BLADE, 3);
        Serial.print(",");
        Serial.print(lcx);
        Serial.println();
    }

    lcx++;
}
