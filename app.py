"""Streamlit UI for the Agentic RFP Evaluation and Supplier Ranking project.

Run locally:   streamlit run app.py
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date

import pandas as pd
import streamlit as st

from rfp_eval import config, db
from rfp_eval.llm import PROVIDERS, LLMError, get_client
from rfp_eval.orchestrator import EvaluationError, SupplierInput, run_evaluation, validate_inputs
from rfp_eval.pdf_tool import PDFExtractionError, extract_text
from rfp_eval.ranking import CriteriaError, TIE_BREAK_RULES, validate_criteria

st.set_page_config(page_title="Agentic RFP Evaluation", page_icon=":material/fact_check:", layout="wide")
db.init_db()


# ----------------------------------------------------------------------------- helpers
def secret(name: str, default: str = "") -> str:
    """Read a setting from the environment first, then Streamlit secrets (if a secrets file exists)."""
    if os.environ.get(name):
        return os.environ[name]
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


@st.cache_data(show_spinner=False)
def preview_pdf(digest: str, data: bytes) -> dict:
    """Extract once per file (cached by content hash) so uploads can be validated immediately."""
    try:
        doc = extract_text(data)
        return {"ok": True, "pages": doc.pages, "chars": doc.chars, "error": ""}
    except PDFExtractionError as exc:
        return {"ok": False, "pages": 0, "chars": 0, "error": str(exc)}


def default_name(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    for suffix in ("_RFP_Response", "_RFP", "_Proposal"):
        stem = stem.replace(suffix, "")
    return stem.replace("_", " ").replace("-", " ").strip()


def to_date(value) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("AI provider")
    default_provider = secret("RFP_PROVIDER", "mock")
    provider = st.selectbox("Provider", list(PROVIDERS), format_func=PROVIDERS.get,
                            index=list(PROVIDERS).index(default_provider) if default_provider in PROVIDERS else 2)
    model = base_url = api_key = ""
    if provider == "anthropic":
        model = st.text_input("Model", secret("ANTHROPIC_MODEL", config.DEFAULT_ANTHROPIC_MODEL))
        api_key = st.text_input("API key", type="password", value="", placeholder="uses ANTHROPIC_API_KEY secret if empty") \
            or secret("ANTHROPIC_API_KEY")
    elif provider == "openai":
        model = st.text_input("Model", secret("OPENAI_MODEL", config.DEFAULT_OPENAI_MODEL))
        base_url = st.text_input("Base URL (optional)", secret("OPENAI_BASE_URL"))
        api_key = st.text_input("API key", type="password", value="", placeholder="uses OPENAI_API_KEY secret if empty") \
            or secret("OPENAI_API_KEY")
    else:
        st.info("Offline mock: a keyword heuristic, not a real LLM. Use it to try the app without an API key.")
        if provider == "mock_faulty":
            st.warning("This mode returns deliberately malformed output so you can watch the validation layer fix it.")
    st.caption("Keys entered here live only in this browser session and are never written to the database.")
    st.divider()
    st.caption("The LLM judges proposal content. Python alone calculates scores, benchmarks, PPI, tie-breaks and ranks.")

st.title("Agentic RFP Evaluation and Supplier Ranking")

tab_criteria, tab_input, tab_results, tab_history = st.tabs(
    ["1. Criteria", "2. Suppliers and evaluate", "3. Results", "4. Past runs"])

# ----------------------------------------------------------------------------- 1. criteria
with tab_criteria:
    all_criteria = db.get_all_criteria()
    active = [c for c in all_criteria if c["is_active"]]
    st.subheader("Active evaluation criteria")
    total_w = sum(c["weight"] for c in active)
    if active:
        st.dataframe(
            pd.DataFrame(active)[["criterion_id", "name", "description", "weight", "max_score"]].rename(
                columns={"criterion_id": "ID", "name": "Criterion", "description": "What the LLM inspects",
                         "weight": "Weight (%)", "max_score": "Max score"}),
            hide_index=True, width="stretch")
    try:
        validate_criteria(active)
        st.success(f"Active weights total {total_w:g}%.")
    except CriteriaError as exc:
        st.error(f"{exc} Evaluation is disabled until this is fixed.")

    with st.expander("Edit criteria and weights"):
        st.caption("Changes are saved to SQLite and are picked up by the next evaluation - no code changes needed.")
        edited = st.data_editor(
            pd.DataFrame(all_criteria), hide_index=True, width="stretch", key="criteria_editor",
            disabled=["criterion_id", "name"],
            column_config={
                "criterion_id": "ID", "name": "Criterion", "description": "Description",
                "weight": st.column_config.NumberColumn("Weight (%)", min_value=0.0, max_value=100.0, step=1.0),
                "max_score": st.column_config.NumberColumn("Max score", min_value=1.0, step=1.0),
                "is_active": st.column_config.CheckboxColumn("Active"),
            })
        c1, c2 = st.columns(2)
        if c1.button("Save changes"):
            db.update_criteria(edited.to_dict("records"))
            st.rerun()
        if c2.button("Scale active weights to total 100%", help="Proportionally rescales active weights."):
            records = edited.to_dict("records")
            act = [r for r in records if r["is_active"]]
            total = sum(float(r["weight"]) for r in act)
            if total > 0:
                for r in act:
                    r["weight"] = round(float(r["weight"]) * 100 / total, 2)
                biggest = max(act, key=lambda r: r["weight"])      # absorb rounding remainder
                biggest["weight"] = round(biggest["weight"] + 100 - sum(r["weight"] for r in act), 2)
                db.update_criteria(records)
                st.rerun()
        with st.form("add_criterion", clear_on_submit=True):
            st.markdown("**Add a criterion**")
            n1, n2, n3, n4 = st.columns([2, 4, 1, 1])
            new_name = n1.text_input("Name")
            new_desc = n2.text_input("What should the LLM inspect?")
            new_w = n3.number_input("Weight", 0.0, 100.0, 0.0)
            new_max = n4.number_input("Max score", 1.0, 100.0, 10.0)
            if st.form_submit_button("Add (inactive until weights total 100%)"):
                if not new_name.strip():
                    st.error("Name is required.")
                else:
                    try:
                        db.add_criterion(new_name, new_desc, new_w, new_max, is_active=False)
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not add criterion: {exc}")

# ----------------------------------------------------------------------------- 2. input
with tab_input:
    st.subheader("Upload supplier proposals")
    uploads = st.file_uploader("Supplier RFP responses (PDF)", type=["pdf"], accept_multiple_files=True)
    st.caption("Try the four synthetic proposals in the `sample_rfps/` folder.")

    inputs: list[SupplierInput] = []
    form_errors: list[str] = []
    if uploads:
        rows, previews = [], {}
        for f in uploads:
            data = f.getvalue()
            pv = preview_pdf(hashlib.sha256(data).hexdigest(), data)
            previews[f.name] = (data, pv)
            rows.append({"File": f.name, "Supplier name": default_name(f.name), "Submission date": date.today(),
                         "Experience rating (0-10)": 5.0, "Pages": pv["pages"], "Characters": pv["chars"],
                         "Status": "OK" if pv["ok"] else pv["error"]})
        signature = hashlib.md5("|".join(f"{f.name}:{f.size}" for f in uploads).encode()).hexdigest()
        st.markdown("**Supplier details** (edit the table)")
        table = st.data_editor(
            pd.DataFrame(rows), hide_index=True, width="stretch", key=f"suppliers_{signature}",
            disabled=["File", "Pages", "Characters", "Status"],
            column_config={
                "Submission date": st.column_config.DateColumn("Submission date", format="YYYY-MM-DD"),
                "Experience rating (0-10)": st.column_config.NumberColumn(
                    "Experience rating (0-10)", min_value=config.EXPERIENCE_MIN, max_value=config.EXPERIENCE_MAX,
                    step=0.1, format="%.1f"),
            })
        for rec in table.to_dict("records"):
            data, pv = previews[rec["File"]]
            if not pv["ok"]:
                form_errors.append(f"{rec['File']}: {pv['error']}")
            sub_date = to_date(rec["Submission date"])
            rating = rec["Experience rating (0-10)"]
            inputs.append(SupplierInput(
                supplier_name=str(rec["Supplier name"] or "").strip(),
                submission_date=sub_date, experience_rating=rating if pd.notna(rating) else None,
                filename=rec["File"], pdf_bytes=data))
        form_errors += validate_inputs(inputs)
        for rec in table.to_dict("records"):
            d = to_date(rec["Submission date"])
            if d and d > date.today():
                st.warning(f"{rec['File']}: submission date {d} is in the future.")

    try:
        validate_criteria(db.get_active_criteria())
        criteria_ok = True
    except CriteriaError as exc:
        criteria_ok = False
        form_errors.append(str(exc))

    for msg in dict.fromkeys(form_errors):
        st.error(msg, icon=":material/error:")

    if st.button("Evaluate suppliers", type="primary", disabled=bool(form_errors) or not uploads):
        try:
            client = get_client(provider, model, api_key, base_url)
        except LLMError as exc:
            st.error(str(exc))
        else:
            bar = st.progress(0.0, text="Starting...")
            try:
                result = run_evaluation(inputs, client, progress=lambda f, m: bar.progress(min(f, 1.0), text=m))
                st.session_state["result"] = result
                bar.empty()
                if result["status"] == "COMPLETED_WITH_WARNINGS":
                    st.warning(f"Run {result['rfp_run_id']} completed with {len(result['warnings'])} warning(s). "
                               "Open the Results tab > Run details.")
                else:
                    st.success(f"Run {result['rfp_run_id']} completed. Open the Results tab.")
            except EvaluationError as exc:
                bar.empty()
                st.error(f"Evaluation failed: {exc}")

# ----------------------------------------------------------------------------- 3. results
def render_results(result: dict) -> None:
    suppliers = result["suppliers"]
    crit = result["criteria"]
    st.caption(f"Run `{result['rfp_run_id']}` | {result['created_at']} | provider: {result['provider']} "
               f"({result['model']}) | status: {result['status']}")
    if result["provider"].startswith("mock"):
        st.info("This run used the offline mock provider (keyword heuristic), not a real LLM.")

    sub_lb, sub_card, sub_run = st.tabs(["Leaderboard", "Detailed scorecard", "Run details"])

    with sub_lb:
        lb = pd.DataFrame([{
            "Rank": s["final_rank"], "Supplier": s["supplier_name"],
            "Absolute score (0-100)": s["absolute_score"], "PPI": s["ppi"],
            "Submission date": s["submission_date"], "Experience rating": s["experience_rating"],
            "Evaluation": s["evaluation_status"]} for s in suppliers])
        st.dataframe(lb, hide_index=True, width="stretch", column_config={
            "Absolute score (0-100)": st.column_config.NumberColumn(format="%.2f"),
            "PPI": st.column_config.NumberColumn(format="%.2f",
                                                  help="Peer Performance Index: weighted average of relative-performance %"),
            "Experience rating": st.column_config.NumberColumn(format="%.1f")})
        st.bar_chart(lb.set_index("Supplier")[["Absolute score (0-100)", "PPI"]], horizontal=True)
        st.markdown("**Why this order?**")
        for line in result["tie_break_explanations"]:
            st.markdown(f"- {line}")

    with sub_card:
        names = [s["supplier_name"] for s in suppliers]
        pick = st.selectbox("Supplier", names, format_func=lambda n: f"#{names.index(n) + 1}  {n}")
        s = next(x for x in suppliers if x["supplier_name"] == pick)
        m1, m2, m3 = st.columns(3)
        m1.metric("Final rank", f"#{s['final_rank']} of {len(suppliers)}")
        m2.metric("Absolute weighted score", f"{s['absolute_score']:.2f} / 100")
        m3.metric("Peer Performance Index", f"{s['ppi']:.2f}")
        if s["evaluation_status"] == "failed":
            st.error("This supplier could not be evaluated; its scores are placeholders (0).")
        st.dataframe(pd.DataFrame([{
            "Criterion": c["name"], "Weight (%)": c["weight"], "Score": c["score"], "Max": c["max_score"],
            "Benchmark": c["benchmark"], "Gap": c["gap"], "Relative %": c["relative_pct"],
            "Weighted points": c["weighted_contribution"], "PPI points": c["ppi_contribution"],
            "Validation": c["status"]} for c in s["criteria"]]),
            hide_index=True, width="stretch", column_config={
                "Weight (%)": st.column_config.NumberColumn(format="%.1f"),
                "Score": st.column_config.NumberColumn(format="%.2f"),
                "Benchmark": st.column_config.NumberColumn(format="%.2f"),
                "Gap": st.column_config.NumberColumn(format="%.2f"),
                "Relative %": st.column_config.NumberColumn(format="%.1f"),
                "Weighted points": st.column_config.NumberColumn(format="%.2f"),
                "PPI points": st.column_config.NumberColumn(format="%.2f")})
        st.markdown("**Evidence and justification**")
        for c in s["criteria"]:
            with st.expander(f"{c['name']} - {c['score']:g}/{c['max_score']:g}  (weight {c['weight']:g}%)"):
                st.markdown(f"**Justification:** {c['justification'] or '_none_'}")
                if c["evidence"]:
                    mark = {True: "verified in document", False: "NOT found verbatim in document"}.get(
                        c["evidence_verified"], "unchecked")
                    st.markdown(f"**Evidence** ({mark}):")
                    st.markdown(f"> {c['evidence']}")
                else:
                    st.markdown("**Evidence:** _none quoted_")
                st.caption(f"Benchmark {c['benchmark']:g} | gap {c['gap']:+g} | relative {c['relative_pct']:.1f}% | "
                           f"{c['weighted_contribution']:.2f} weighted points")
        if s["risks"]:
            st.markdown("**Risks and gaps flagged**")
            for r in s["risks"]:
                st.markdown(f"- {r}")
        if s["overall_summary"]:
            st.markdown(f"**Summary:** {s['overall_summary']}")

    with sub_run:
        st.markdown(f"**RFP_RUN_ID:** `{result['rfp_run_id']}`")
        st.markdown("**Tie-break order**")
        for i, rule in enumerate(result.get("tie_break_rules", TIE_BREAK_RULES), start=1):
            st.markdown(f"{i}. {rule}")
        for line in result["tie_break_explanations"]:
            st.markdown(f"- {line}")
        st.markdown(f"**Warnings ({len(result['warnings'])})**")
        if result["warnings"]:
            for w in result["warnings"]:
                st.warning(w)
        else:
            st.success("No validation warnings.")
        st.markdown("**Criteria used (snapshot)**")
        st.dataframe(pd.DataFrame(crit)[["criterion_id", "name", "weight", "max_score"]], hide_index=True)
        if result.get("agent_trace"):
            with st.expander("Agent trace (tool calls in order)"):
                st.dataframe(pd.DataFrame(result["agent_trace"]), hide_index=True, width="stretch")
        with st.expander("Formulas"):
            st.markdown(
                "- **Absolute score** = sum of (score / max score) x weight\n"
                "- **Benchmark** = highest valid score for the criterion across all suppliers\n"
                "- **Gap** = score - benchmark (0 for the leader, otherwise negative)\n"
                "- **Relative %** = score / benchmark x 100 (100 if the benchmark is 0, i.e. everyone is tied)\n"
                "- **PPI** = weighted average of relative % using the criterion weights")
        st.download_button("Download complete result (JSON)", json.dumps(result, indent=2, default=str),
                           file_name=f"{result['rfp_run_id']}.json", mime="application/json", type="primary")


with tab_results:
    if "result" in st.session_state:
        render_results(st.session_state["result"])
    else:
        st.info("No results yet. Upload proposals and click **Evaluate suppliers**, or load a past run.")

# ----------------------------------------------------------------------------- 4. history
with tab_history:
    runs = db.list_runs()
    if not runs:
        st.info("No runs stored yet.")
    else:
        st.dataframe(pd.DataFrame(runs), hide_index=True, width="stretch")
        chosen = st.selectbox("Load a stored run", [r["rfp_run_id"] for r in runs])
        if st.button("Load run into Results tab"):
            loaded = db.load_run(chosen)
            if loaded and loaded["suppliers"]:
                st.session_state["result"] = loaded
                st.rerun()
            else:
                st.error("That run has no stored supplier results (it may have failed).")
