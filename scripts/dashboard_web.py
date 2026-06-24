"""
GreenTrain AI — web dashboard (Streamlit + Plotly).
Pulls from AWS backend (/state, /session/{id}) and re-renders every N seconds.

Run:
  streamlit run scripts/dashboard_web.py

Browser opens automatically at http://localhost:8501.
"""
import sys
import time
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from greentrain_agent import GreenTrainClient

st.set_page_config(page_title="GreenTrain AI", page_icon="🌱", layout="wide")

STATE_COLORS = {
    "GREEN":  "#22c55e",
    "YELLOW": "#eab308",
    "RED":    "#ef4444",
    "ERR":    "#94a3b8",
}
STATE_FILL = {
    "GREEN":  "rgba(34,197,94,0.10)",
    "YELLOW": "rgba(234,179,8,0.12)",
    "RED":    "rgba(239,68,68,0.15)",
}


@st.cache_resource
def get_client():
    return GreenTrainClient()


def default_session() -> str:
    p = ROOT / ".active_session"
    return p.read_text().strip() if p.exists() else ""


st.sidebar.title("⚙️  Config")
session_id = st.sidebar.text_input(
    "Session ID",
    value=default_session(),
    help="Auto-loaded from .active_session when train_demo.py --remote is running",
)
refresh_s = st.sidebar.slider("Refresh interval (s)", 1, 10, 2)
sample_limit = st.sidebar.slider("Sample window", 30, 200, 120)

client = get_client()

st.sidebar.markdown("---")
demo_mode = st.sidebar.toggle(
    "🛠️  Demo override mode",
    value=False,
    help=(
        "켜면 실제 한국 grid 데이터를 무시하고 수동으로 GREEN/YELLOW/RED 강제할 수 있음. "
        "발표 시간 압축용. 평소엔 꺼둠 — carbon_judge Lambda가 15분마다 자동 갱신함."
    ),
)
if demo_mode:
    st.sidebar.warning(
        "⚠️ Demo mode 활성 — 버튼 누르면 실제 한국 grid 데이터를 1분간 override함."
    )
    sim_col1, sim_col2, sim_col3 = st.sidebar.columns(3)
    if sim_col1.button("🟢 GREEN", use_container_width=True):
        client.simulate("GREEN", 1)
    if sim_col2.button("🟡 YELLOW", use_container_width=True):
        client.simulate("YELLOW", 1)
    if sim_col3.button("🔴 RED", use_container_width=True):
        client.simulate("RED", 1)
else:
    st.sidebar.caption(
        "🟢 정상 운영 모드 — ElectricityMap에서 한국 grid 실시간 데이터로만 작동."
    )



def render_state_banner(state_data: dict) -> None:
    state = state_data.get("state", "ERR")
    color = STATE_COLORS.get(state, "#94a3b8")
    intensity = state_data.get("carbon_g_kwh")
    intensity_s = f"{intensity:.0f}" if intensity is not None else "—"
    source = state_data.get("source") or "—"
    zone = state_data.get("zone") or "—"
    updated = state_data.get("updated_at") or "—"
    sim_until = state_data.get("sim_until")
    is_override = source == "simulator" and sim_until

    if is_override:
        st.markdown(
            f"""
            <div style="background:#fef3c7;border:2px dashed #f59e0b;color:#78350f;
                        padding:10px 16px;border-radius:8px;text-align:center;margin-bottom:8px;
                        font-weight:600;font-size:13px;">
              ⚠️ DEMO OVERRIDE ACTIVE — 실제 한국 grid 데이터 무시 중 · until {sim_until}
            </div>
            """,
            unsafe_allow_html=True,
        )

    source_label = (
        "🟡 simulator (demo override)" if source == "simulator"
        else f"🟢 {source}" if source == "electricitymap"
        else f"⚪ {source}"
    )

    st.markdown(
        f"""
        <div style="background:{color};color:white;padding:24px 28px;border-radius:14px;
                    text-align:center;box-shadow:0 8px 24px rgba(0,0,0,0.08);">
          <div style="font-size:13px;opacity:0.85;letter-spacing:2px;">KOREAN GRID</div>
          <div style="font-size:56px;font-weight:800;margin:6px 0;line-height:1;">{state}</div>
          <div style="font-size:20px;font-weight:500;">
            {intensity_s} gCO₂/kWh · zone <b>{zone}</b>
          </div>
          <div style="font-size:13px;opacity:0.9;margin-top:8px;">source · {source_label}</div>
          <div style="font-size:11px;opacity:0.75;margin-top:4px;">updated · {updated}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def add_state_overlay(fig: go.Figure, df: pd.DataFrame) -> None:
    if "state" not in df.columns or df.empty:
        return
    prev = None
    seg_start = None
    for i in range(len(df)):
        s = df.iloc[i]["state"]
        if s != prev:
            if prev is not None and seg_start is not None:
                fig.add_vrect(
                    x0=df.iloc[seg_start]["ts"],
                    x1=df.iloc[i]["ts"],
                    fillcolor=STATE_FILL.get(prev, "rgba(0,0,0,0)"),
                    line_width=0,
                    layer="below",
                )
            seg_start = i
            prev = s
    if prev is not None and seg_start is not None:
        fig.add_vrect(
            x0=df.iloc[seg_start]["ts"],
            x1=df.iloc[-1]["ts"],
            fillcolor=STATE_FILL.get(prev, "rgba(0,0,0,0)"),
            line_width=0,
            layer="below",
        )


def render_session(session_data: dict, session_id: str, state_data: dict | None = None) -> None:
    samples = session_data.get("samples") or []
    if not samples:
        st.info(f"세션 `{session_id}` 에 아직 메트릭 없음. `train_demo.py --remote` 실행 중인지 확인.")
        return

    df = pd.DataFrame(samples)
    df["ts"] = pd.to_datetime(df["ts"], unit="ms")
    latest = session_data.get("latest") or samples[-1]

    cur_state = latest.get("state", "GREEN")
    cur_color = STATE_COLORS.get(cur_state, "#0ea5e9")

    # --- Row 1: current snapshot ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current Power", f"{float(latest.get('power_w', 0)):.1f} W")
    c2.metric("Utilization", f"{int(latest.get('util_pct', 0))} %")
    c3.metric("Σ Energy used", f"{float(latest.get('cumulative_energy_wh', 0)):.3f} Wh")
    c4.metric("Σ CO₂ emitted", f"{float(latest.get('cumulative_co2_g', 0)):.3f} g")

    # --- Row 2: savings (counterfactual: had we not throttled at all) ---
    # Approximations:
    #   peak_power  ~ max recent power_w   (proxy for "full speed")
    #   idle_power  = 5 W                  (typical RTX idle)
    #   throttle_s  = cumulative sleep injected so far
    #   saved_wh   = (peak - idle) * throttle_s / 3600
    #   avoided_g  = saved_wh * current_grid_intensity / 1000
    #   won_saved  = saved_wh / 1000 * KRW_PER_KWH
    KRW_PER_KWH = 150.0  # Korean residential mid-tier average
    IDLE_POWER_W = 5.0

    powers = [float(s.get("power_w", 0)) for s in samples]
    peak_power = max(powers) if powers else 0.0
    throttle_s = float(latest.get("cumulative_throttle_seconds", 0))
    compute_s = float(latest.get("cumulative_compute_seconds", 0))

    saved_wh = max(0.0, (peak_power - IDLE_POWER_W) * throttle_s / 3600.0)
    grid_intensity = state_data.get("carbon_g_kwh") if state_data else None
    grid_intensity = float(grid_intensity) if grid_intensity else 450.0  # KR default
    avoided_g = saved_wh * grid_intensity / 1000.0
    won_saved = saved_wh / 1000.0 * KRW_PER_KWH
    time_penalty_pct = (throttle_s / compute_s * 100.0) if compute_s > 0 else 0.0

    st.markdown("##### 🟢 절감량 — throttle 안 했더라면 vs 실제")
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Energy saved", f"{saved_wh:.3f} Wh",
              help=f"(peak {peak_power:.0f}W - idle 5W) × {throttle_s:.1f}s throttle")
    s2.metric("CO₂ avoided", f"{avoided_g:.3f} g",
              help=f"saved Wh × {grid_intensity:.0f} gCO₂/kWh (실시간 한국 grid)")
    s3.metric("₩ saved", f"₩ {won_saved:.2f}",
              help=f"@ ₩{KRW_PER_KWH:.0f}/kWh — hackathon에선 작아 보여도 24h 학습 × 1년이면 의미 있음")
    s4.metric("Time penalty", f"+{time_penalty_pct:.1f} %",
              help="학습이 throttle 때문에 길어진 비율 (compute 대비 sleep)")
    s5.metric("Throttled", f"{throttle_s:.1f} s",
              help=f"누적 sleep 주입 시간 (compute {compute_s:.1f}s)")

    fig = go.Figure()
    add_state_overlay(fig, df)
    fig.add_trace(go.Scatter(
        x=df["ts"], y=df["power_w"],
        mode="lines",
        line=dict(color=cur_color, width=2.5),
        fill="tozeroy",
        fillcolor=f"rgba(14,165,233,0.12)",
        name="Power (W)",
        hovertemplate="%{x|%H:%M:%S}<br><b>%{y:.1f} W</b><extra></extra>",
    ))
    fig.update_layout(
        height=420,
        margin=dict(l=40, r=20, t=10, b=40),
        xaxis_title=None,
        yaxis_title="GPU Power (W)",
        yaxis=dict(rangemode="tozero"),
        showlegend=False,
        hovermode="x unified",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridcolor="rgba(148,163,184,0.15)")
    st.markdown(f"#### Power · `{session_id}` · {len(df)} samples")
    st.plotly_chart(fig, use_container_width=True, key="chart_power")

    cc1, cc2 = st.columns(2)
    with cc1:
        fig_util = go.Figure()
        add_state_overlay(fig_util, df)
        fig_util.add_trace(go.Scatter(
            x=df["ts"], y=df["util_pct"],
            mode="lines",
            line=dict(color="#8b5cf6", width=2),
            fill="tozeroy",
            fillcolor="rgba(139,92,246,0.12)",
            hovertemplate="%{x|%H:%M:%S}<br><b>%{y} %</b><extra></extra>",
        ))
        fig_util.update_layout(
            height=260,
            margin=dict(l=40, r=20, t=30, b=40),
            title="GPU Utilization (%)",
            yaxis=dict(range=[0, 100]),
            showlegend=False,
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_util.update_yaxes(showgrid=True, gridcolor="rgba(148,163,184,0.15)")
        st.plotly_chart(fig_util, use_container_width=True, key="chart_util")

    with cc2:
        fig_e = go.Figure()
        if "cumulative_energy_wh" in df.columns:
            fig_e.add_trace(go.Scatter(
                x=df["ts"], y=df["cumulative_energy_wh"],
                mode="lines",
                line=dict(color="#10b981", width=2.5),
                name="Energy (Wh)",
                hovertemplate="%{x|%H:%M:%S}<br><b>%{y:.4f} Wh</b><extra></extra>",
            ))
        if "cumulative_co2_g" in df.columns:
            fig_e.add_trace(go.Scatter(
                x=df["ts"], y=df["cumulative_co2_g"],
                mode="lines",
                line=dict(color="#f59e0b", width=2.5, dash="dot"),
                name="CO₂ (g)",
                yaxis="y2",
                hovertemplate="%{x|%H:%M:%S}<br><b>%{y:.4f} g</b><extra></extra>",
            ))
        fig_e.update_layout(
            height=260,
            margin=dict(l=40, r=40, t=30, b=40),
            title="Cumulative Energy + CO₂",
            yaxis=dict(title="Wh"),
            yaxis2=dict(title="g", overlaying="y", side="right"),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            plot_bgcolor="rgba(0,0,0,0)",
        )
        fig_e.update_yaxes(showgrid=True, gridcolor="rgba(148,163,184,0.15)")
        st.plotly_chart(fig_e, use_container_width=True, key="chart_energy")


try:
    state_data = client._request("GET", "/state")
except Exception as e:
    state_data = {"state": "ERR", "source": f"fetch failed: {e}"}

session_data = None
if session_id:
    try:
        session_data = client.get_session(session_id, limit=sample_limit)
    except Exception:
        session_data = None

render_state_banner(state_data)
st.markdown("")
if session_id:
    if session_data:
        render_session(session_data, session_id, state_data)
    else:
        st.warning(f"세션 `{session_id}` 조회 실패.")
else:
    st.info("사이드바에 Session ID를 입력하거나 `train_demo.py --remote` 를 실행하세요.")

# Re-run after refresh_s seconds. Streamlit's idiomatic live-dashboard pattern:
# each rerun is a fresh script execution so element keys are not duplicated.
time.sleep(refresh_s)
st.rerun()
