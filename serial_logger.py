import json
import os
import time
import uuid
from pathlib import Path

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
RUNS_DIR.mkdir(exist_ok=True)

ACTIVE_RUN_PATH = RUNS_DIR / "active_run.json"
LIVE_CONTROL_PATH = RUNS_DIR / "live_control.json"
CSV_HEADER = "t_us,pressV,pressPsi,loadKg,rpm\n"


def available_ports():
    if serial is None:
        return []
    return [p.device for p in serial.tools.list_ports.comports()]


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: Path, payload, retries: int = 20, delay: float = 0.05):
    last_error = None

    for _ in range(retries):
        temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
                f.flush()
                os.fsync(f.fileno())

            os.replace(temp_path, path)
            return

        except PermissionError as e:
            last_error = e
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            time.sleep(delay)

        except Exception:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            raise

    raise last_error


def write_active_run(active: bool, session_name: str, csv_path: Path, port: str, baud: int):
    payload = {
        "active": active,
        "run_name": session_name,
        "csv_path": str(csv_path),
        "port": port,
        "baud": baud,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_json(ACTIVE_RUN_PATH, payload)


def initialize_live_control():
    if not LIVE_CONTROL_PATH.exists():
        payload = {
            "recording": False,
            "run_name": "",
            "current_run_csv": "",
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        write_json(LIVE_CONTROL_PATH, payload)


def write_live_control(recording: bool, run_name: str, current_run_csv: str):
    payload = {
        "recording": recording,
        "run_name": run_name,
        "current_run_csv": current_run_csv,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_json(LIVE_CONTROL_PATH, payload)


def prompt_for_port():
    ports = available_ports()
    if not ports:
        raise RuntimeError("No serial ports found.")

    print("Available ports:")
    for i, port in enumerate(ports, start=1):
        print(f"  {i}. {port}")

    while True:
        choice = input("Select port number: ").strip()
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(ports):
                return ports[idx]
        except ValueError:
            pass
        print("Invalid selection. Try again.")


def prompt_for_baud():
    default_baud = 115200
    raw = input(f"Baud rate [{default_baud}]: ").strip()
    if raw == "":
        return default_baud
    return int(raw)


def prompt_for_session_name():
    session_name = input("Session name [session]: ").strip()
    return session_name or "session"


def make_session_csv_path(session_name: str) -> Path:
    safe_name = session_name.strip().replace(" ", "_") or "session"
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return RUNS_DIR / f"{safe_name}_{timestamp}.csv"


def make_run_csv_path(run_name: str) -> Path:
    safe_name = run_name.strip().replace(" ", "_") or "run"
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    return RUNS_DIR / f"{safe_name}_{timestamp}.csv"


def is_valid_data_line(line: str) -> bool:
    if not line or line.startswith("t_us,"):
        return False

    parts = line.split(",")
    if len(parts) != 5:
        return False

    try:
        float(parts[0])
        float(parts[1])
        float(parts[2])
        float(parts[3])
        float(parts[4])
    except ValueError:
        return False

    return True


def open_run_file(run_name: str):
    run_csv_path = make_run_csv_path(run_name)
    f = open(run_csv_path, "w", encoding="utf-8", newline="")
    f.write(CSV_HEADER)
    f.flush()
    print(f"[RUN STARTED] Writing run CSV: {run_csv_path.name}")
    return run_csv_path, f


def close_run_file(run_csv_path, run_file):
    if run_file is not None:
        run_file.flush()
        run_file.close()
    if run_csv_path is not None:
        print(f"[RUN STOPPED] Finalized run CSV: {run_csv_path.name}")


def main():
    if serial is None:
        raise RuntimeError("pyserial is not installed. Run: python -m pip install pyserial")

    port = prompt_for_port()
    baud = prompt_for_baud()
    session_name = prompt_for_session_name()
    session_csv_path = make_session_csv_path(session_name)

    print()
    print(f"Opening {port} @ {baud}")
    print(f"Logging source session to {session_csv_path}")
    print("Use Streamlit to send Start and Stop commands.")
    print("Press Ctrl+C to stop the logger.")
    print()

    with open(session_csv_path, "w", encoding="utf-8", newline="") as f:
        f.write(CSV_HEADER)
        f.flush()

    write_active_run(True, session_name, session_csv_path, port, baud)
    initialize_live_control()
    write_live_control(False, "", "")

    current_run_file = None
    current_run_csv_path = None
    current_recording_state = False

    try:
        with serial.Serial(port, baud, timeout=1) as ser:
            time.sleep(2.0)
            ser.reset_input_buffer()

            with open(session_csv_path, "a", encoding="utf-8", newline="") as session_file:
                while True:
                    control = read_json(
                        LIVE_CONTROL_PATH,
                        {"recording": False, "run_name": "", "current_run_csv": "", "updated_at": ""}
                    )

                    desired_recording = bool(control.get("recording", False))
                    desired_run_name = str(control.get("run_name", "")).strip() or "run"

                    if desired_recording and not current_recording_state:
                        current_run_csv_path, current_run_file = open_run_file(desired_run_name)
                        current_recording_state = True
                        write_live_control(True, desired_run_name, str(current_run_csv_path))

                    elif (not desired_recording) and current_recording_state:
                        finished_run_csv = str(current_run_csv_path) if current_run_csv_path is not None else ""
                        close_run_file(current_run_csv_path, current_run_file)
                        current_run_file = None
                        current_run_csv_path = None
                        current_recording_state = False
                        write_live_control(False, desired_run_name, finished_run_csv)

                    raw = ser.readline()
                    if not raw:
                        continue

                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue

                    print(line)

                    if not is_valid_data_line(line):
                        continue

                    session_file.write(line + "\n")
                    session_file.flush()

                    if current_recording_state and current_run_file is not None:
                        current_run_file.write(line + "\n")
                        current_run_file.flush()

                    write_active_run(True, session_name, session_csv_path, port, baud)

    except KeyboardInterrupt:
        print("\nStopping logger...")

    finally:
        close_run_file(current_run_csv_path, current_run_file)
        write_active_run(False, session_name, session_csv_path, port, baud)
        write_live_control(False, "", "")
        print(f"Final session CSV saved to: {session_csv_path}")


if __name__ == "__main__":
    main()