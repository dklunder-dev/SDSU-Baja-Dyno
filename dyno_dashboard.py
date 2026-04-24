import io
import json
import os
import time
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st

st.set_page_config(page_title="Dyno Dashboard", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "runs"
RUNS_DIR.mkdir(exist_ok=True)

ACTIVE_RUN_PATH = RUNS_DIR / "active_run.json"
LIVE_CONTROL_PATH = RUNS_DIR / "live_control.json"

REQUIRED_COLUMNS = ["t_us", "pressV", "pressPsi", "loadKg", "rpm"]


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


def ensure_live_control():
    if not LIVE_CONTROL_PATH.exists():
        write_json(
            LIVE_CONTROL_PATH,
            {
                "recording": False,
                "run_name": "",
                "current_run_csv": "",
                "updated_at": "",
            },
        )


def set_recording(recording: bool, run_name: str):
    current = read_json(
        LIVE_CONTROL_PATH,
        {"recording": False, "run_name": "", "current_run_csv": "", "updated_at": ""}
    )

    payload = {
        "recording": recording,
        "run_name": run_name.strip(),
        "current_run_csv": current.get("current_run_csv", ""),
        "updated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    write_json(LIVE_CONTROL_PATH, payload)


def load_dyno_csv(file_obj) -> pd.DataFrame:
    df = pd.read_csv(file_obj)

    if not set(REQUIRED_COLUMNS).issubset(df.columns):
        if hasattr(file_obj, "seek"):
            file_obj.seek(0)
            df = pd.read_csv(file_obj, names=REQUIRED_COLUMNS)
        else:
            df = pd.read_csv(file_obj, names=REQUIRED_COLUMNS)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    for col in REQUIRED_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=REQUIRED_COLUMNS).reset_index(drop=True)
    if df.empty:
        raise ValueError("No valid data rows found.")

    df["time_s"] = (df["t_us"] - df["t_us"].iloc[0]) / 1_000_000.0
    return df


def add_calcs(df: pd.DataFrame, lever_arm_m: float | None, smooth_window: int) -> pd.DataFrame:
    df = df.copy()
    df["force_N"] = df["loadKg"] * 9.80665

    if lever_arm_m and lever_arm_m > 0:
        df["torque_Nm"] = df["force_N"] * lever_arm_m
        df["power_W"] = df["torque_Nm"] * df["rpm"] * (2 * np.pi / 60.0)
        df["power_hp"] = df["power_W"] / 745.7

    for col in ["pressPsi", "loadKg", "rpm", "force_N", "torque_Nm", "power_hp"]:
        if col in df.columns:
            df[f"{col}_smooth"] = df[col].rolling(
                window=smooth_window,
                center=True,
                min_periods=1
            ).mean()

    return df


def make_plot(x1, y1, label1, ylabel, title, x2=None, y2=None, label2=None):
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(x1, y1, label=label1)
    if x2 is not None and y2 is not None:
        ax.plot(x2, y2, label=label2)
    ax.set_xlabel("Time (s)" if title.endswith("vs Time") else "RPM")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def summary_block(df: pd.DataFrame, label: str):
    dt = df["time_s"].diff().dropna()
    rate_hz = (1.0 / dt.mean()) if len(dt) else np.nan

    st.subheader(label)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Samples", f"{len(df)}")
    c2.metric("Duration", f"{df['time_s'].iloc[-1]:.2f} s")
    c3.metric("Sample Rate", f"{rate_hz:.1f} Hz" if not np.isnan(rate_hz) else "N/A")
    c4.metric("Max RPM", f"{df['rpm'].max():.1f}")


def render_compare_view(primary_df: pd.DataFrame, smooth_window: int, lever_arm_m: float, comparison_df: pd.DataFrame | None = None):
    primary_df = add_calcs(primary_df, lever_arm_m if lever_arm_m > 0 else None, smooth_window)

    if comparison_df is not None:
        comparison_df = add_calcs(comparison_df, lever_arm_m if lever_arm_m > 0 else None, smooth_window)

    summary_col1, summary_col2 = st.columns(2)
    with summary_col1:
        summary_block(primary_df, "Primary Run")
    with summary_col2:
        if comparison_df is not None:
            summary_block(comparison_df, "Comparison Run")

    st.subheader("Time Series")
    plot_col1, plot_col2 = st.columns(2)

    with plot_col1:
        st.pyplot(make_plot(
            primary_df["time_s"], primary_df["pressPsi_smooth"], "Primary",
            "Pressure (psi)", "Pressure vs Time",
            comparison_df["time_s"] if comparison_df is not None else None,
            comparison_df["pressPsi_smooth"] if comparison_df is not None else None,
            "Comparison" if comparison_df is not None else None
        ))
        st.pyplot(make_plot(
            primary_df["time_s"], primary_df["rpm_smooth"], "Primary",
            "RPM", "RPM vs Time",
            comparison_df["time_s"] if comparison_df is not None else None,
            comparison_df["rpm_smooth"] if comparison_df is not None else None,
            "Comparison" if comparison_df is not None else None
        ))

    with plot_col2:
        st.pyplot(make_plot(
            primary_df["time_s"], primary_df["loadKg_smooth"], "Primary",
            "Load (kg)", "Load vs Time",
            comparison_df["time_s"] if comparison_df is not None else None,
            comparison_df["loadKg_smooth"] if comparison_df is not None else None,
            "Comparison" if comparison_df is not None else None
        ))
        if "power_hp_smooth" in primary_df.columns:
            st.pyplot(make_plot(
                primary_df["rpm"], primary_df["power_hp_smooth"], "Primary",
                "Power (hp)", "Power vs RPM",
                comparison_df["rpm"] if comparison_df is not None and "power_hp_smooth" in comparison_df.columns else None,
                comparison_df["power_hp_smooth"] if comparison_df is not None and "power_hp_smooth" in comparison_df.columns else None,
                "Comparison" if comparison_df is not None else None
            ))
        else:
            st.info("Enter a lever arm length in the sidebar to calculate torque and power.")

    st.subheader("Data Preview")
    st.dataframe(primary_df.head(20), use_container_width=True)

    csv_buffer = io.StringIO()
    primary_df.to_csv(csv_buffer, index=False)
    st.download_button(
        label="Download processed primary run CSV",
        data=csv_buffer.getvalue(),
        file_name="processed_primary_run.csv",
        mime="text/csv",
    )


st.title("Dyno Dashboard")

ensure_live_control()

if "last_active_run" not in st.session_state:
    st.session_state.last_active_run = None

active_run = read_json(ACTIVE_RUN_PATH, None)
if active_run is not None:
    st.session_state.last_active_run = active_run
else:
    active_run = st.session_state.last_active_run

live_control = read_json(
    LIVE_CONTROL_PATH,
    {"recording": False, "run_name": "", "current_run_csv": "", "updated_at": ""}
)

with st.sidebar:
    st.header("Settings")
    lever_arm_m = st.number_input("Lever arm length (m)", min_value=0.0, value=0.0, step=0.01)
    smooth_window = st.slider("Smoothing window", min_value=1, max_value=25, value=5, step=2)

live_tab, compare_tab = st.tabs(["Live Run", "Upload and Compare"])

with live_tab:
    st.caption("Manual Start, Stop, and Refresh Graph. Logger owns the serial port and creates the run CSVs.")

    if active_run is None:
        st.warning("No active serial logger found. Start serial_logger.py first.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.write(f"**Logger Status:** {'Logging' if active_run.get('active', False) else 'Stopped'}")
        c2.write(f"**Session Name:** {active_run.get('run_name', 'N/A')}")
        c3.write(f"**Source File:** {Path(active_run.get('csv_path', '')).name}")

        run_name = st.text_input("Run label", value="pull_1", key="live_run_name")
        is_recording = bool(live_control.get("recording", False))

        b1, b2, b3 = st.columns(3)

        with b1:
            if st.button("Start Run", disabled=is_recording):
                set_recording(True, run_name)
                st.success(f"Start command sent for run: {run_name}")
                st.rerun()

        with b2:
            if st.button("Stop Run", disabled=not is_recording):
                set_recording(False, run_name)
                time.sleep(0.25)
                st.rerun()

        with b3:
            if st.button("Refresh Graph"):
                st.rerun()

        st.subheader("Current Command State")
        st.json(live_control)

        current_run_csv = live_control.get("current_run_csv", "").strip()

        if current_run_csv:
            run_path = Path(current_run_csv)

            if run_path.exists():
                try:
                    df = load_dyno_csv(run_path)
                    df = add_calcs(df, lever_arm_m if lever_arm_m > 0 else None, smooth_window)

                    latest1, latest2, latest3, latest4 = st.columns(4)
                    latest1.metric("Latest Pressure", f"{df['pressPsi'].iloc[-1]:.2f} psi")
                    latest2.metric("Latest Load", f"{df['loadKg'].iloc[-1]:.3f} kg")
                    latest3.metric("Latest RPM", f"{df['rpm'].iloc[-1]:.1f}")
                    if "power_hp" in df.columns:
                        latest4.metric("Latest Power", f"{df['power_hp'].iloc[-1]:.2f} hp")
                    else:
                        latest4.metric("Latest Power", "N/A")

                    max1, max2, max3, max4 = st.columns(4)
                    max1.metric("Max Pressure", f"{df['pressPsi'].max():.2f} psi")
                    max2.metric("Max Load", f"{df['loadKg'].max():.3f} kg")
                    max3.metric("Max RPM", f"{df['rpm'].max():.1f}")
                    if "power_hp" in df.columns:
                        max4.metric("Max Power", f"{df['power_hp'].max():.2f} hp")
                    else:
                        max4.metric("Max Power", "N/A")

                    p1, p2 = st.columns(2)

                    with p1:
                        st.pyplot(make_plot(df["time_s"], df["pressPsi_smooth"], "Run", "Pressure (psi)", "Pressure vs Time"))
                        st.pyplot(make_plot(df["time_s"], df["rpm_smooth"], "Run", "RPM", "RPM vs Time"))

                    with p2:
                        st.pyplot(make_plot(df["time_s"], df["loadKg_smooth"], "Run", "Load (kg)", "Load vs Time"))
                        if "power_hp_smooth" in df.columns:
                            st.pyplot(make_plot(df["rpm"], df["power_hp_smooth"], "Run", "Power (hp)", "Power vs RPM"))
                        else:
                            st.info("Enter a lever arm length in the sidebar to calculate torque and power.")

                    st.subheader("Run Data Preview")
                    st.dataframe(df.tail(20), use_container_width=True)

                except Exception as e:
                    st.warning(f"Could not load run CSV yet: {e}")
            else:
                st.info("A run CSV path is known, but the file does not exist yet.")
        else:
            st.info("No run CSV selected yet. Click Start Run first.")

        st.subheader("Files in runs folder")
        run_files = sorted(RUNS_DIR.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)

        if run_files:
            for f in run_files[:20]:
                st.write(f.name)
        else:
            st.info("No CSV files found yet.")

with compare_tab:
    st.caption("Upload dyno CSV files to compare runs.")

    compare_mode = st.checkbox("Enable run comparison")

    col1, col2 = st.columns(2)
    with col1:
        uploaded_1 = st.file_uploader("Primary run CSV", type=["csv"], key="run1")
    with col2:
        uploaded_2 = st.file_uploader("Comparison run CSV", type=["csv"], key="run2") if compare_mode else None

    if uploaded_1 is None:
        st.info("Upload a dyno CSV to get started.")
    else:
        try:
            primary_df = load_dyno_csv(uploaded_1)
        except Exception as e:
            st.error(f"Could not load primary run: {e}")
        else:
            comparison_df = None
            if uploaded_2 is not None:
                try:
                    comparison_df = load_dyno_csv(uploaded_2)
                except Exception as e:
                    st.error(f"Could not load comparison run: {e}")

            render_compare_view(primary_df, smooth_window, lever_arm_m, comparison_df)