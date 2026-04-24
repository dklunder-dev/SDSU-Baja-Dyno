# Dyno Logging and Dashboard

- `serial_logger.py` handles Arduino serial logging and creates CSV files
- `dyno_dashboard.py` is the Streamlit dashboard for run control and graphing
- `run_all.bat` launches both automatically on Windows


### Source Logging
The logger continuously records a **source session file** while it is running. This is what the original commad file is. This is why the first step exists. If you don't nothing will load. 
FYI: its like this bc streamlit cant save to csv and update live graphs at the same time 
Example:

```text
session_20260423_153549.csv
```

### Individual Runs
When you press **Start Run** and **Stop Run** in the dashboard, the logger creates a separate CSV for that run (basically it takes a section of the fat CSV). 

Examples:

```text
pull_1_2026-04-23_15-44-50.csv
pull_2_2026-04-23_15-51-12.csv
```
^ they are just snapshots in the big CSV 


## Requirements

Install Python first.

Python 3.9 or newer is recommended.

Then install the required packages:

```bash
pip install -r requirements.txt
```

---

## Arduino Setup

1. Connect the Arduino to your computer
2. Open the Arduino IDE
3. Load the provided `Dyno_logging.ino` sketch
4. Select the correct board and COM port
5. Upload the sketch
6. Make sure the baud rate in the Arduino code is:

```text
115200
```
^ you can find it on the bottom right








---

## How to Run ******************************************************************************************************

## Option 1: Easiest * 99% OF THE TIME JUST RUN THIS ONE 
Double click:

```text
run_all.bat
```

This opens:
- one terminal for `serial_logger.py`
- one terminal for the Streamlit dashboard

## Option 2: Manual
Open **two terminals** in the project folder.

### Terminal 1
```bash
python serial_logger.py
```

### Terminal 2
```bash
python -m streamlit run dyno_dashboard.py
```

---

## How to Use It

### Start the Logger
When you launch in the command line window `serial_logger.py`, it will ask for:

- COM port
- baud rate
- session name

It then starts recording the main source session file.

### Start a Run
In the dashboard:
1. Enter a run label such as `pull_1`
2. Click **Start Run**

### Stop a Run
Click **Stop Run**

The logger will finalize a CSV for that run automatically.

### Refresh the Graph
Click **Refresh Graph** whenever you want to update the live plot.

This is a manual refresh workflow by design because it has proven stable.

---
## Stopping the Logger  

In the logger terminal, press:

```text
Ctrl + C
```

This cleanly stops the logger and finalizes the source session file.
  ******************************************************************************************************



## Files Created

All output is saved in the `runs/` folder.

### Source Session File
Created when the logger starts:

```text
session_name_YYYYMMDD_HHMMSS.csv
```
So basically whatever you named it then the date 

### Run Files
Created when a run is started and stopped:

```text
run_name_YYYY-MM-DD_HH-MM-SS.csv
```
So basically whatever you named it then the date 


### Internal JSON Files
These are used for communication between the logger and dashboard:

- `active_run.json`
- `live_control.json`

Do not edit these while the system is running.

---

## How the Two Programs Communicate

The logger and dashboard are two separate programs.

They communicate using JSON files in the `runs/` folder.





## Important Notes

- Do **not** open Arduino Serial Monitor while the logger is running  (only one can read at a time, this case it is pythpn)
- Run both scripts from the same project folder
- The logger is the only process that owns the serial port

---

## Troubleshooting

### Streamlit is not recognized
Use:

```bash
python -m streamlit run dyno_dashboard.py
```

### No COM ports found
- make sure the Arduino is connected
- check drivers
- verify the board appears in Arduino IDE


### Run file was not created
- Make sure you are reading the serial logger
- make sure you clicked **Start Run**
- then **Stop Run**
- check the `runs/` folder

### Logger says access denied on JSON
This was handled by the current retry-safe JSON writer in the scripts. If it happens again, close extra apps reading the same folder.

---

## Why the Architecture Is Split

Earlier versions I tried to let Streamlit read serial directly.

That was unreliable because:
- Streamlit reruns the script frequently
- serial logging wants a stable continuous process
- COM port ownership is sensitive

The current version is more robust:

- `serial_logger.py` handles serial data acquisition
- `dyno_dashboard.py` handles UI and graphing
- JSON files pass simple control and status messages between them

---

