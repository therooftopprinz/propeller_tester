import serial
import time
import argparse
import sys

def main():
    parser = argparse.ArgumentParser(description='Propeller PWM Sweep Program')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='Serial port (default: /dev/ttyUSB1)')
    parser.add_argument('--baud', type=int, default=115200, help='Baud rate (default: 115200)')
    parser.add_argument('--start', type=int, default=1000, help='Start PWM value (default: 1000)')
    parser.add_argument('--end', type=int, default=2000, help='End PWM value (default: 2000)')
    parser.add_argument('--increment', type=int, default=100, help='PWM increment step (default: 100)')
    parser.add_argument('--wait', type=float, default=2.0, help='Stabilization time in seconds (default: 2.0)')
    parser.add_argument('--output', help='Output file (default: stdout)')
    args = parser.parse_args()

    # Validate PWM range
    if not (1000 <= args.start <= 2000 and 1000 <= args.end <= 2000):
        print("Error: PWM values must be between 1000 and 2000", file=sys.stderr)
        sys.exit(1)

    try:
        # Setup serial connection
        with serial.Serial(args.port, args.baud, timeout=1) as ser:
            ser.write('T\n'.encode())
            ser.flush()
            time.sleep(2)
            # Open output file or use stdout
            f = open(args.output, 'w') if args.output else sys.stdout

            # PWM sweep loop
            pwm_values = range(args.start, args.end + 1, args.increment)
            for pwm in pwm_values:
                # Send PWM command
                ser.write(f'P {pwm}\n'.encode())
                ser.flush()

                # Wait for stabilization
                time.sleep(args.wait)
                
                # Read and process data
                ser.reset_input_buffer()
                line = ser.readline().decode().strip()
                
                # Validate and output data
                if line and line.count(',') == 4:
                    f.write(line + '\n')

                f.flush()

            ser.write('P 0\n'.encode())
            ser.flush()
            # Close file if not stdout
            if args.output:
                f.close()

    except serial.SerialException as e:
        print(f"Serial port error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()