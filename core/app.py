import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go
import math
import json
import os
import qrcode
from io import BytesIO

from fsrs import Card

# ====================== YOUR EXISTING MODULES ======================
from database import (
    initDB, toDF, updateDB, getAdaptData, get_due_count,
    connectDB, MAIN_TABLE
)
from universal_scheduler import UniversalScheduler
from utils import stateDefault, SCHEDULING_DEFAULT, CONTENT_EMPTY

# ========================== CONFIG ==========================
st.set_page_config(
    page_title="Adapt • SRS Trainer",
    page_icon="🏃‍♂️",
    layout="wide"
)

st.markdown("""
<style>
    .main {padding-top: 2rem;}
    h1, h2, h3 {font-family: 'Segoe UI', system-ui, sans-serif;}
    .stButton>button {border-radius: 8px; height: 42px; font-weight: 500;}
    .card {background-color: rgba(255,255,255,0.05); padding: 20px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1);}
</style>
""", unsafe_allow_html=True)

# ========================== TUNING PERSISTENCE ==========================
TUNING_FILE = "tuning_settings.json"

def load_tuning_settings():
    defaults = {"fitness_multiplier": 6.0, "exertion_level": 12.0, "kp": 0.055, "fatigue_multiplier": 0.35}
    if os.path.exists(TUNING_FILE):
        try:
            with open(TUNING_FILE, "r") as f:
                saved = json.load(f)
                defaults.update(saved)
        except:
            pass
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def save_tuning_settings():
    data = {
        "fitness_multiplier": st.session_state.fitness_multiplier,
        "exertion_level": st.session_state.exertion_level,
        "kp": st.session_state.kp,
        "fatigue_multiplier": st.session_state.fatigue_multiplier
    }
    with open(TUNING_FILE, "w") as f:
        json.dump(data, f)

load_tuning_settings()

if "scheduler" not in st.session_state:
    initDB()
    st.session_state.scheduler = UniversalScheduler({"m": 0.35, "kp": st.session_state.kp})

if "test_data_loaded" not in st.session_state:
    st.session_state.test_data_loaded = False

if "revealed" not in st.session_state:
    st.session_state.revealed = set()

# ========================== QR CODE GENERATOR ==========================
def get_qr_code():
    url = "https://adapt-app-qjvbekhs2r2a9tqjult9wd.streamlit.app"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a1a", back_color="#ffffff")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ========================== SIDEBAR (with QR Code) ==========================
st.sidebar.title("Adapt App")
st.sidebar.image(get_qr_code(), caption="📱 Scan to open on phone", use_column_width=True)
page = st.sidebar.radio("Navigation", ["Dashboard", "Review", "Create Card", "View All", "Graphs", "Tuning"])
# ========================== HELPERS (unchanged) ==========================
def reset_all_due_dates():
    now = datetime.now(timezone.utc).isoformat(timespec='milliseconds')
    with connectDB() as conn:
        conn.execute(f"UPDATE {MAIN_TABLE} SET due = ?", (now,))
        conn.execute(f"""
            UPDATE {MAIN_TABLE}
            SET state = json_set(state, '$.peakFitness', 0, '$.fitness', 0, '$.fatigue', 0),
                 scheduling = json_set(scheduling, '$.S', 0.1, '$.D', 5.0, '$.R', NULL, '$.tauG', 7.0,
                                       '$.state', 2, '$.step', 0, '$.lastReview', NULL, '$.exertion', 0)
            WHERE json_extract(content, '$.type') = 'run'
        """)
        conn.commit()
    st.success("✅ Full reset completed")
    st.rerun()

def boost_demo_curves():
    df = toDF()
    fixed = 0
    for _, row in df.iterrows():
        if row.get('content') and '"type": "run"' in str(row['content']):
            data = getAdaptData(row['id'])
            data["state"]["peakFitness"] = 80.0
            data["state"]["fitness"] = 80.0
            data["scheduling"]["exertion"] = st.session_state.exertion_level
            updateDB(None, data["scheduling"], data["state"], row['id'])
            fixed += 1
    st.success(f"✅ Boosted {fixed} run cards!")
    st.rerun()

def load_test_data():
    if st.session_state.test_data_loaded:
        return
    if len(toDF()) > 0:
        st.session_state.test_data_loaded = True
        return

    test_cards = [
        {"type": "text", "cue": "What is the capital of France?", "response": "Paris"},
        {"type": "text", "cue": "What is 7 × 8?", "response": "56"},
        {"type": "run", "cue": "5km run", "baseline": "1500", "target": "1200", "netDirection": "negative"},
        {"type": "run", "cue": "10km run", "baseline": "3000", "target": "2400", "netDirection": "negative"},
    ]

    for card in test_cards:
        content = CONTENT_EMPTY.copy()
        content.update(card)
        updateDB(content_dict=content, scheduling_dict=SCHEDULING_DEFAULT, state_dict=stateDefault())
    
    st.session_state.test_data_loaded = True

# ========================== SIDEBAR ==========================
st.sidebar.title("Adapt App")
page = st.sidebar.radio("Navigation", ["Dashboard", "Review", "Create Card", "View All", "Graphs", "Tuning"])

load_test_data()

# ========================== PAGES (clean & professional) ==========================
if page == "Dashboard":
    st.title("🏠 Dashboard")
    due_count = get_due_count()
    total = len(toDF())
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Cards", total)
    col2.metric("Due Today", due_count)
    col3.metric("Review Streak", "N/A")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Full Reset", type="primary"):
            reset_all_due_dates()
    with col2:
        if st.button("🛠️ Boost Run Cards", type="secondary"):
            boost_demo_curves()

elif page == "Review":
    st.title("📚 Review Session")
    df = toDF()
    due_df = df[df['due'] <= datetime.now(timezone.utc).isoformat(timespec='milliseconds')]

    if due_df.empty:
        st.success("🎉 No cards due right now!")
        st.info("Use the Reset button on the Dashboard to test again.")
    else:
        st.write(f"**{len(due_df)} cards due**")
        for idx, row in due_df.iterrows():
            data = getAdaptData(row['id'])
            content = data["content"]
            card_type = content.get("type")

            with st.container(border=True):
                st.subheader(f"Card #{row['id']}")

                if card_type == "text":
                    st.write(f"**Cue:** {content.get('cue')}")
                    st.text_input("Your answer", key=f"input_{row['id']}")
                    if st.button("Reveal Correct Answer", key=f"reveal_{row['id']}"):
                        st.session_state.revealed.add(row['id'])
                    if row['id'] in st.session_state.revealed:
                        st.success(f"**Correct Response:** {content.get('response')}")
                        rating = st.radio("How well did you do?", ["Again (1)", "Hard (2)", "Good (3)", "Easy (4)"], key=f"rate_{row['id']}", horizontal=True)
                        if st.button("Submit Review", key=f"submit_{row['id']}"):
                            grade = {"Again (1)": 0, "Hard (2)": 1, "Good (3)": 2, "Easy (4)": 3}[rating]
                            scheduling_dict, state_dict, new_due = st.session_state.scheduler.SchedulerReview(data, grade)
                            updateDB(content_dict=None, scheduling_dict=scheduling_dict, state_dict=state_dict, adapt_id=row['id'], due=new_due)
                            st.success("✅ Review saved!")
                            st.rerun()

                elif card_type == "run":
                    st.write(f"**Cue:** {content.get('cue')}")
                    if st.button("I finished the run", key=f"finished_{row['id']}"):
                        st.session_state[f"run_finished_{row['id']}"] = True
                    if st.session_state.get(f"run_finished_{row['id']}", False):
                        st.text_input("Your time (seconds)", key=f"time_{row['id']}")
                        rating = st.radio("How well did you do?", ["Again (1)", "Hard (2)", "Good (3)", "Easy (4)"], key=f"rate_run_{row['id']}", horizontal=True)
                        if st.button("Submit Review", key=f"submit_run_{row['id']}"):
                            grade = {"Again (1)": 0, "Hard (2)": 1, "Good (3)": 2, "Easy (4)": 3}[rating]
                            data["scheduling"]["exertion"] = st.session_state.exertion_level
                            scheduling_dict, state_dict, new_due = st.session_state.scheduler.SchedulerReview(data, grade)
                            state_dict["peakFitness"] = max(state_dict.get("peakFitness", 0), 25.0) * st.session_state.fitness_multiplier
                            state_dict["fitness"] = state_dict["peakFitness"]
                            state_dict["fatigue"] = max(state_dict.get("fatigue", 0), 12.0) * st.session_state.fatigue_multiplier
                            updateDB(content_dict=None, scheduling_dict=scheduling_dict, state_dict=state_dict, adapt_id=row['id'], due=new_due)
                            st.success("✅ Review saved!")
                            st.rerun()

                st.divider()

elif page == "Create Card":
    st.title("✨ Create New Adaptation")
    card_type = st.radio("Type of card", ["Text", "Run"], horizontal=True)
    with st.form("create_form", clear_on_submit=True):
        if card_type == "Text":
            cue = st.text_input("Cue")
            response = st.text_input("Response")
            if st.form_submit_button("Create Text Card") and cue and response:
                content = CONTENT_EMPTY.copy()
                content.update({"type": "text", "cue": cue, "response": response})
                updateDB(content_dict=content, scheduling_dict=SCHEDULING_DEFAULT, state_dict=stateDefault())
                st.success("✅ Text card created!")
                st.balloons()
        else:
            cue = st.text_input("Cue (e.g. '5km run')")
            baseline = st.number_input("Baseline time (seconds)", value=1500)
            target = st.number_input("Target time (seconds)", value=1200)
            if st.form_submit_button("Create Run Card") and cue:
                content = CONTENT_EMPTY.copy()
                content.update({"type": "run", "cue": cue, "baseline": str(baseline), "target": str(target), "netDirection": "negative"})
                updateDB(content_dict=content, scheduling_dict=SCHEDULING_DEFAULT, state_dict=stateDefault())
                st.success("✅ Run card created!")
                st.balloons()

elif page == "View All":
    st.title("📋 All Adaptations")
    df = toDF()
    st.dataframe(df, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        if st.button("📤 Export All Data"):
            json_data = df.to_json(orient="records")
            st.download_button("Download JSON", json_data, file_name="adaptations_backup.json", mime="application/json")
    with col2:
        uploaded = st.file_uploader("📥 Import JSON", type=["json"])
        if uploaded:
            imported = pd.read_json(uploaded)
            st.success(f"Imported {len(imported)} cards")

elif page == "Graphs":
    st.title("📈 Performance Graphs")
    df = toDF()
    if df.empty:
        st.warning("No cards yet.")
    else:
        card_options = [f"Card #{int(row['id'])} — {str(row['content'])[:50]}..." for _, row in df.iterrows()]
        selected = st.selectbox("Select a card to analyze", card_options)
        card_id = int(selected.split("#")[1].split("—")[0].strip())
        data = getAdaptData(card_id)

        content = data["content"]
        state = data["state"]
        scheduling = data["scheduling"]

        st.subheader(f"Card #{card_id} — {content.get('cue', 'Untitled')}")
        st.caption(f"Peak Fitness: {state['peakFitness']:.1f} | Fatigue: {state['fatigue']:.1f}")

        days = list(range(0, 366))
        fitness_values = []
        fatigue_values = []
        predicted_values = []
        r_final_values = []
        crossing_day = None

        peak_fitness = state["peakFitness"]
        fatigue_0 = state["fatigue"]
        kp = st.session_state.kp
        tau_g = scheduling.get("tauG", 7.0)
        net_direction = content.get("netDirection", "negative")
        sign = -1 if net_direction == "negative" else 1

        card_dict = {
            "card_id": card_id,
            "stability": scheduling.get("S") or 0.1,
            "difficulty": scheduling.get("D") or 5.0,
            "last_review": scheduling.get("lastReview"),
            "due": data.get("due"),
            "state": scheduling.get("state", 2),
            "step": scheduling.get("step", 0),
        }
        temp_card = Card.from_json(json.dumps(card_dict))

        today = datetime.now(timezone.utc)
        baseline = float(content.get("baseline") or 0)
        target = float(content.get("target") or 0)

        crossings = 0
        previous_r = None

        for d in days:
            future_dt = today + timedelta(days=d)
            r_fitness = st.session_state.scheduler.fsrs.get_card_retrievability(temp_card, current_datetime=future_dt)
            fitness_t = peak_fitness * r_fitness
            fatigue_t = fatigue_0 * math.exp(-d / tau_g)
            net_t = fitness_t - fatigue_t
            predicted_t = baseline + sign * net_t

            fitness_values.append(fitness_t)
            fatigue_values.append(fatigue_t)
            predicted_values.append(predicted_t)

            if content.get("type") == "run":
                r_final = 1 / (1 + math.exp(-kp * (target - predicted_t)))
                r_final_values.append(r_final)

                if previous_r is not None:
                    if previous_r >= 0.9 and r_final < 0.9:
                        crossings += 1
                        if crossings == 2:
                            crossing_day = d
                previous_r = r_final

        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(x=days, y=fitness_values, name="Fitness", line=dict(color="green")))
        fig1.add_trace(go.Scatter(x=days, y=fatigue_values, name="Fatigue", line=dict(color="red")))
        fig1.add_trace(go.Scatter(x=days, y=predicted_values, name="Predicted Performance", line=dict(color="blue", width=3)))
        if baseline > 0:
            fig1.add_hline(y=baseline, line_dash="dash", annotation_text="Baseline", line_color="gray")
        if target > 0:
            fig1.add_hline(y=target, line_dash="dot", annotation_text="Target", line_color="orange")
        fig1.update_layout(title="Fitness, Fatigue & Predicted Performance (1 Year)", xaxis_title="Days from today", yaxis_title="Value")
        st.plotly_chart(fig1, use_container_width=True)

        if content.get("type") == "run" and r_final_values:
            fig2 = go.Figure()
            fig2.add_trace(go.Scatter(x=days, y=r_final_values, name="R_final (System)", line=dict(color="purple", width=3)))
            fig2.add_hline(y=0.9, line_dash="dash", annotation_text="0.9 Threshold", line_color="orange")
            if crossing_day is not None:
                fig2.add_vline(x=crossing_day, line_dash="dot", line_color="gold")
                fig2.add_annotation(x=crossing_day, y=0.9, text="2nd 0.9 Crossing", showarrow=True, arrowhead=2)
            fig2.update_layout(title="R_final (Sigmoid) — Second crossing of 0.9", xaxis_title="Days from today", yaxis_title="R_final (0–1)")
            st.plotly_chart(fig2, use_container_width=True)

elif page == "Tuning":
    st.title("⚙️ Tuning Parameters")
    st.write("Adjust these values live — they affect reviews and graphs immediately.")

    st.session_state.fitness_multiplier = st.slider("Fitness Multiplier on Review", 1.0, 10.0, st.session_state.fitness_multiplier, 0.1)
    st.session_state.exertion_level = st.slider("Exertion Level on Run Review", 1.0, 20.0, st.session_state.exertion_level, 0.5)
    st.session_state.kp = st.slider("kp (sigmoid steepness)", 0.001, 0.1, st.session_state.kp, 0.001)
    st.session_state.fatigue_multiplier = st.slider("Fatigue Gain Multiplier", 0.1, 2.0, st.session_state.fatigue_multiplier, 0.05)

    save_tuning_settings()

    st.info("✅ Settings are auto-saved.")

st.sidebar.caption("Adapt App MVP • Streamlit")