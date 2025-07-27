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
constexpr double VOLT_PER_TICK = 0.04881;
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

    void add_sample(T n)
    {
        samples[idx] = n;
        idx++;
        if (idx>=N)
        {
            idx = 0;
        }
    }

    T get_sample()
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
    operator bool()
    {
        unsigned long now = millis();
        if (now - last >= interval)
        {
            last = now;
            return true;
        }
        return false;
    }
};

template <unsigned N>
class data_sampler
{
public:
    float value()
    {
        return values.get_sample();
    }
protected:
    average_window<N> values;
    schedule_context scheduler;
};

class LoadCell : public data_sampler<3>
{
public:
    void begin(int dt, int ck, int scale)
    {
        device.begin(dt, ck);
        device.set_scale(scale);
    }
    
    void schedule()
    {
        if (scheduler)
        {
            values.add_sample(device.get_units(1));
        }
    }

    HX711 device;
};

template <int tag>
class TachoMeter : public data_sampler<15>
{
public:
    void begin(int pin)
    {
        pinMode(pin, INPUT_PULLUP);
        attachInterrupt(digitalPinToInterrupt(pin), TachoMeter<tag>::isr, RISING);    
    }

    void schedule()
    {
        if (scheduler)
        {
            float rpm = 60 * count * (1000.0 / scheduler.interval);
            count = 0;
            values.add_sample(rpm);
        }
    }

    schedule_context scheduler;
    static unsigned int count;
    static void isr()
    {
        count++;
    }
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

class CurrentSensor : public data_sampler<10>
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
            values.add_sample((voltage - currentOffset) / (MV_PER_AMP / 1000.0));
        }
    }
private:
    int pin;
    float currentOffset;
};

class VoltageSensor : public data_sampler<10>
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
            values.add_sample(analogRead(pin) * VOLT_PER_TICK);
        }
    }
private:
    int pin;
};

LoadCell Thrust;
TachoMeter<0> RPM;
template<> unsigned int TachoMeter<0>::count = 0;
ServoTimer1 Motor;
CurrentSensor Current;
VoltageSensor Voltage;

// Output
schedule_context CSVLogSchedule;

void setup()
{
    Serial.begin(115200);
    Thrust.begin(HX711_DT, HX711_SCK, 360);
    RPM.begin(TACHO);
    Motor.begin(ESC_PWM);
    Current.begin(CURRENT_SENSOR);
    Voltage.begin(VOLTAGE_SENSOR);

    Serial.println("Ready!");
    Serial.println("Format: time(ms),load(g),current(A),voltage(V),angspeed(RPM)");
}

void clearRx()
{
    while (Serial.available() && Serial.read() != '\n');
}

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
            Serial.println("Factor");
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

    if (CSVLogSchedule)
    {
        Serial.print(CSVLogSchedule.last);
        Serial.print(",");
        Serial.print(Thrust.value(), 1);
        Serial.print(",");
        Serial.print(Current.value(), 3);
        Serial.print(",");
        Serial.print(Voltage.value(), 3);
        Serial.print(",");
        Serial.print(RPM.value()/N_BLADE, 3);
        Serial.println();
    }

    delay(1);
}
