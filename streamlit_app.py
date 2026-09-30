from __future__ import annotations

import json
import os
from html import escape
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from domain_assistant import DomainAssistant
from solution.solution import BenchmarkRunner, QAPair, RAGASEvaluator


ROOT = Path(__file__).resolve().parent
GOLDEN_PATH = ROOT / "golden_dataset.json"
ACTUAL_PATH = ROOT / "artifacts" / "actual_answers.json"
JUDGE_PATH = ROOT / "artifacts" / "llm_judge_results.json"
load_dotenv(ROOT / ".env")

st.set_page_config(
    page_title="OrbitTech · Lab đánh giá AI",
    page_icon="◩",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@400;500;600;700&display=swap');
    :root { --ink:#111; --muted:#707070; --line:#e8e8e8; --green:#18885b; --red:#bf453e; }
    html, body, [class*="css"] { font-family:'DM Sans',sans-serif; color:var(--ink); }
    .stApp { background:#fff; }
    [data-testid="stHeader"] { background:rgba(255,255,255,.92); }
    [data-testid="stSidebar"] { background:#fafafa; border-right:1px solid var(--line); }
    [data-testid="stSidebar"] > div:first-child { padding-top:1.1rem; }
    .block-container { max-width:1440px; padding:4.25rem 2.5rem 3rem; }
    .brand-row { display:flex; align-items:center; justify-content:space-between; border-bottom:1px solid var(--line); padding:0 0 1rem; }
    .brand { display:flex; align-items:center; gap:.65rem; color:#111; font-weight:700; font-size:1.05rem; letter-spacing:0; }
    .brand-mark { width:25px; height:25px; display:grid; place-items:center; background:#111; color:white; font-size:.75rem; }
    .brand-meta { color:#777; font-family:'DM Mono',monospace; font-size:.72rem; }
    .spectrum { height:3px; margin:0 0 2.3rem; background:linear-gradient(90deg,#ffd84c 0%,#ff8b50 27%,#ec5b8d 48%,#8b7cff 68%,#43d7be 100%); }
    .eyebrow { color:#777; font:500 .7rem 'DM Mono',monospace; text-transform:uppercase; letter-spacing:.08em; }
    .page-title { color:#111; font-size:2rem; line-height:1.14; letter-spacing:0; font-weight:600; margin:.5rem 0 .35rem; }
    .page-subtitle { color:#666; font-size:.96rem; margin:0 0 1.5rem; }
    .section-label { font:500 .72rem 'DM Mono',monospace; text-transform:uppercase; color:#777; letter-spacing:.06em; border-bottom:1px solid var(--line); padding-bottom:.55rem; margin:1rem 0 .85rem; }
    .message-user { background:#f5f5f5; padding:1rem 1.1rem; border-left:2px solid #111; margin:.7rem 0; }
    .message-assistant { padding:1rem 1.1rem; border-left:2px solid #37bd9a; margin:.7rem 0 1.1rem; line-height:1.65; }
    .message-label { font:500 .68rem 'DM Mono',monospace; color:#777; text-transform:uppercase; margin-bottom:.45rem; }
    .mono { font-family:'DM Mono',monospace; }
    .small-note { color:#777; font-size:.8rem; }
    .status-ok { color:var(--green); font:500 .76rem 'DM Mono',monospace; }
    .status-off { color:var(--red); font:500 .76rem 'DM Mono',monospace; }
    div[data-testid="stMetric"] { border-top:1px solid var(--line); padding-top:.7rem; }
    div[data-testid="stMetricLabel"] { color:#777; font:500 .72rem 'DM Mono',monospace; text-transform:uppercase; }
    div[data-testid="stMetricValue"] { font-size:1.65rem; }
    .stButton button, .stDownloadButton button { border-radius:3px; border:1px solid #111; }
    .stButton button[kind="primary"] { background:#111; color:white; }
    [data-testid="stChatInput"] { border-radius:3px; }
    hr { border-color:var(--line); }
    @media (max-width:800px) { .block-container { padding:4rem 1rem 2rem; } .page-title { font-size:1.65rem; } .spectrum { margin-bottom:1.5rem; } }
    </style>
    """,
    unsafe_allow_html=True,
)


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def get_client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key or key == "your_openai_api_key_here":
        raise RuntimeError("Thêm OPENAI_API_KEY hợp lệ vào file .env để gọi model.")
    return OpenAI(api_key=key)


def api_ready() -> bool:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    return bool(key and key != "your_openai_api_key_here")


def get_assistant() -> DomainAssistant:
    if "assistant" not in st.session_state:
        st.session_state.assistant = DomainAssistant.from_corpus(
            ROOT / "data" / "technology_store",
            answer_language="Vietnamese",
        )
    return st.session_state.assistant


def build_pairs(golden: dict[str, Any], actual: dict[str, Any]) -> tuple[list[QAPair], dict[str, str]]:
    actual_by_id = {item["id"]: item for item in actual.get("answers", [])}
    pairs: list[QAPair] = []
    answers_by_question: dict[str, str] = {}
    for item in golden.get("qa_pairs", []):
        generated = actual_by_id.get(item.get("id"))
        if not generated or not generated.get("actual_answer"):
            continue
        contexts = item.get("contexts", [])
        retrieved = generated.get("retrieved_contexts", [])
        pairs.append(
            QAPair(
                question=item["question"],
                expected_answer=item["expected_answer"],
                context="\n\n".join(row.get("text", "") for row in contexts),
                metadata={"id": item.get("id"), "difficulty": item.get("difficulty")},
                retrieved_contexts=[row.get("text", "") for row in retrieved],
            )
        )
        answers_by_question[item["question"]] = generated["actual_answer"]
    return pairs, answers_by_question


def render_header(page: str) -> None:
    st.markdown(
        f'<div class="brand-row"><div class="brand"><span class="brand-mark">◢</span> OrbitTech <span class="brand-meta">/ PHÒNG LAB ĐÁNH GIÁ AI</span></div><div class="brand-meta">K4 · LEVEL 3A · NGÀY 14</div></div><div class="spectrum"></div><div class="eyebrow">{page} / HỖ TRỢ ORBITTECH</div>',
        unsafe_allow_html=True,
    )


def judge_answer(question: str, answer: str, contexts: list[str]) -> dict[str, Any]:
    from evaluate_with_llm import judge_single_answer

    golden = read_json(GOLDEN_PATH) or {}
    known = next((item for item in golden.get("qa_pairs", []) if item["question"] == question), None)
    expected = known["expected_answer"] if known else "Đánh giá dựa trên bằng chứng đã truy xuất; câu hỏi tự do không có đáp án chuẩn."
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return judge_single_answer(get_client(), model, question, answer, expected, contexts)


def chat_page() -> None:
    render_header("TRÒ CHUYỆN")
    st.markdown('<h1 class="page-title">Trợ lý OrbitTech</h1><p class="page-subtitle">Hỗ trợ khách hàng dựa trên tài liệu và chính sách của OrbitTech.</p>', unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("### Cấu hình trợ lý")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        connected = api_ready()
        st.markdown(f'<span class="{"status-ok" if connected else "status-off"}">{"● ĐÃ CẤU HÌNH API KEY" if connected else "● CHƯA CÓ API KEY"}</span>', unsafe_allow_html=True)
        st.caption(f"Mô hình · `{model}`")
        st.caption("Truy xuất · BM25 · 5 đoạn tài liệu")
        st.divider()
        st.caption("Tài liệu: OrbitTech Store Customer Support · 10 nguồn")
        if st.button("Cuộc trò chuyện mới", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.last_turn = None
            st.rerun()

    history = st.session_state.setdefault("chat_history", [])
    if not history:
        st.markdown('<div class="section-label">GỢI Ý CÂU HỎI</div>', unsafe_allow_html=True)
        suggestions = [
            "Tôi có bao lâu để trả lại thiết bị đã mở hộp?",
            "Tôi nên làm gì khi thiết bị quá nóng?",
            "Tôi có thể đổi quốc gia giao hàng không?",
        ]
        columns = st.columns(3)
        for index, prompt in enumerate(suggestions):
            if columns[index].button(prompt, key=f"suggestion-{index}", use_container_width=True):
                st.session_state.pending_prompt = prompt

    for turn in history:
        st.markdown(f'<div class="message-user"><div class="message-label">BẠN</div>{escape(turn["question"])}</div>', unsafe_allow_html=True)
        safe_answer = escape(turn["answer"]).replace("\n", "<br>")
        st.markdown(f'<div class="message-assistant"><div class="message-label">TRỢ LÝ ORBITTECH · {escape(turn.get("model", ""))}</div>{safe_answer}</div>', unsafe_allow_html=True)
        with st.expander(f"Đoạn tài liệu đã truy xuất · {len(turn.get('contexts', []))}"):
            for context in turn.get("contexts", []):
                st.markdown(f"- {context['source_doc']} · `{context['chunk_id']}` · score `{context['score']:.3f}`")
                st.caption(context["text"])
        if turn.get("judge"):
            st.markdown("**Điểm từ LLM Judge**")
            cols = st.columns(4)
            for col, (label, key) in zip(cols, [("Tổng điểm", "score"), ("Chính xác", "correctness"), ("Liên quan", "relevance"), ("An toàn", "safety")]):
                value = turn["judge"].get("sub_scores", {}).get(key, turn["judge"].get("score", "—"))
                col.metric(label, f"{value}/5")
            st.caption(turn["judge"].get("reasoning_vi", turn["judge"].get("verdict", "")))

    pending = st.session_state.pop("pending_prompt", None)
    with st.form("chat-form", clear_on_submit=True):
        prompt_text = st.text_input(
            "Tin nhắn",
            placeholder="Hỏi về sản phẩm, đơn hàng, đổi trả, bảo hành hoặc an toàn thiết bị",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button("Gửi", type="primary")
    prompt = pending or (prompt_text.strip() if submitted else "")
    if prompt:
        history.append({"question": prompt, "answer": "", "contexts": [], "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini")})
        try:
            with st.spinner("Đang tìm tài liệu phù hợp và tạo câu trả lời…"):
                response = get_assistant().answer_with_trace(prompt)
            history[-1]["answer"] = response.actual_answer
            history[-1]["contexts"] = [
                {"source_doc": chunk.source_doc, "chunk_id": chunk.chunk_id, "score": chunk.score, "text": chunk.text}
                for chunk in response.retrieved_chunks
            ]
            st.session_state.last_turn = len(history) - 1
            st.rerun()
        except Exception as exc:
            history.pop()
            st.error(str(exc))

    last_index = st.session_state.get("last_turn")
    if last_index is not None and last_index < len(history) and history[last_index].get("answer"):
        if st.button("Chấm câu trả lời mới nhất bằng LLM Judge", type="primary"):
            try:
                with st.spinner("LLM Judge đang đối chiếu câu trả lời với tài liệu nguồn…"):
                    turn = history[last_index]
                    turn["judge"] = judge_answer(
                        turn["question"],
                        turn["answer"],
                        [row["text"] for row in turn["contexts"]],
                    )
                st.rerun()
            except Exception as exc:
                st.error(f"LLM Judge gặp lỗi: {exc}")


def benchmark_page() -> None:
    render_header("ĐÁNH GIÁ")
    st.markdown('<h1 class="page-title">Bàn đánh giá</h1><p class="page-subtitle">Bộ câu hỏi chuẩn → câu trả lời RAG → chỉ số → LLM Judge.</p>', unsafe_allow_html=True)
    golden = read_json(GOLDEN_PATH)
    actual = read_json(ACTUAL_PATH)
    judge_report = read_json(JUDGE_PATH)
    if not golden:
        st.error("Không tìm thấy golden_dataset.json hoặc tệp không hợp lệ.")
        return

    total = len(golden.get("qa_pairs", []))
    answers_count = len(actual.get("answers", [])) if actual else 0
    judged_count = judge_report.get("total_evaluated", 0) if judge_report else 0
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Câu hỏi chuẩn", total)
    c2.metric("Câu trả lời đã sinh", answers_count)
    c3.metric("Đã được LLM chấm", judged_count)
    c4.metric("Mô hình", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    if "fresh_results" in st.session_state:
        results = st.session_state.fresh_results
        report = st.session_state.fresh_report
        source_label = "Lượt chạy mới · phiên hiện tại"
    elif actual:
        pairs, answers_by_question = build_pairs(golden, actual)
        results = BenchmarkRunner().run(pairs, lambda question: answers_by_question[question], RAGASEvaluator())
        report = BenchmarkRunner().generate_report(results)
        source_label = "actual_answers.json · chỉ số tính lại trong phiên này"
    else:
        results, report, source_label = [], None, "Chưa có artifact câu trả lời"

    with st.expander("Chạy benchmark mới (20 lượt gọi mô hình thật)"):
        st.caption("Sinh câu trả lời bằng mô hình OpenAI đã cấu hình rồi chấm bằng các chỉ số kiểu RAGAS của lab. Kết quả chỉ lưu trong phiên này, không ghi đè artifact hiện có.")
        if st.button("Sinh câu trả lời và đánh giá", type="primary", disabled=not api_ready()):
            try:
                from domain_assistant import generate_actual_answers

                progress = st.progress(0, text="Đang khởi tạo benchmark…")
                messages: list[str] = []

                def update_progress(message: str) -> None:
                    messages.append(message)
                    completed = min(max((len(messages) - 2) // 2, 0), total)
                    progress.progress(completed / total, text=f"Đang xử lý câu hỏi {completed}/{total}")

                with st.spinner("Đang sinh câu trả lời thật; có thể mất vài phút…"):
                    fresh_actual = generate_actual_answers(
                        GOLDEN_PATH,
                        ROOT / "data" / "technology_store",
                        progress=update_progress,
                    )
                pairs, answer_map = build_pairs(golden, fresh_actual)
                runner = BenchmarkRunner()
                fresh_results = runner.run(pairs, lambda question: answer_map[question], RAGASEvaluator())
                st.session_state.fresh_results = fresh_results
                st.session_state.fresh_report = runner.generate_report(fresh_results)
                st.session_state.fresh_actual = fresh_actual
                st.rerun()
            except Exception as exc:
                st.error(f"Benchmark đã dừng: {exc}")

    if report:
        st.markdown(f'<div class="section-label">TỔNG HỢP · {escape(source_label)}</div>', unsafe_allow_html=True)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Tỷ lệ đạt", f"{report.get('pass_rate', 0):.0%}")
        m2.metric("Bám sát nguồn", f"{report.get('avg_faithfulness', 0):.3f}")
        m3.metric("Liên quan", f"{report.get('avg_relevance', 0):.3f}")
        m4.metric("Đầy đủ", f"{report.get('avg_completeness', 0):.3f}")

        rows = []
        for result in results:
            rows.append({
                "Mã": result.qa_pair.metadata.get("id"),
                "Độ khó": {"easy": "Dễ", "medium": "Trung bình", "hard": "Khó", "adversarial": "Đối kháng"}.get(result.qa_pair.metadata.get("difficulty"), result.qa_pair.metadata.get("difficulty")),
                "Tổng điểm": round(result.overall_score(), 3),
                "Bám sát nguồn": round(result.faithfulness, 3),
                "Liên quan": round(result.relevance, 3),
                "Đầy đủ": round(result.completeness, 3),
                "Bao phủ ngữ cảnh": result.context_recall,
                "Thứ hạng ngữ cảnh": result.context_precision,
                "Trạng thái": "ĐẠT" if result.passed else {"off_topic": "Lạc đề", "hallucination": "Bịa thông tin", "incomplete": "Thiếu ý", "irrelevant": "Không liên quan", "refusal": "Từ chối"}.get(result.failure_type, "CHƯA ĐẠT"),
            })
        st.dataframe(rows, use_container_width=True, hide_index=True)
        failures = [result for result in results if not result.passed]
        if failures:
            st.markdown('<div class="section-label">NHÓM LỖI</div>', unsafe_allow_html=True)
            counts: dict[str, int] = {}
            for result in failures:
                category = {"off_topic": "Lạc đề", "hallucination": "Bịa thông tin", "incomplete": "Thiếu ý", "irrelevant": "Không liên quan", "refusal": "Từ chối"}.get(result.failure_type, "Chưa phân loại")
                counts[category] = counts.get(category, 0) + 1
            st.write(" · ".join(f"{name}: {count}" for name, count in counts.items()))
            with st.expander("Xem các trường hợp điểm thấp nhất"):
                for item in sorted(failures, key=lambda row: row.overall_score())[:5]:
                    failure_name = {"off_topic": "Lạc đề", "hallucination": "Bịa thông tin", "incomplete": "Thiếu ý", "irrelevant": "Không liên quan", "refusal": "Từ chối"}.get(item.failure_type, "Chưa phân loại")
                    st.markdown(f"**{item.qa_pair.metadata.get('id')} · {item.overall_score():.3f} · {failure_name}**")
                    st.write(item.qa_pair.question)
                    st.caption(item.actual_answer)
    else:
        st.info(source_label)

    st.markdown('<div class="section-label">CHẤM ĐIỂM BẰNG LLM JUDGE</div>', unsafe_allow_html=True)
    st.caption("Chọn một câu để chấm bằng rubric chuyên biệt của OrbitTech.")
    source_actual = st.session_state.get("fresh_actual") or actual
    actual_records = source_actual.get("answers", []) if source_actual else []
    if actual_records:
        by_id = {row["id"]: row for row in actual_records}
        choices = [row for row in golden.get("qa_pairs", []) if row["id"] in by_id]
        question_by_id = {row["id"]: row["question"] for row in choices}
        selected_id = st.selectbox("Câu hỏi trong bộ chuẩn", list(question_by_id), format_func=lambda key: f"{key} · {question_by_id[key][:76]}")
        selected = next(row for row in choices if row["id"] == selected_id)
        if st.button("Chấm câu hỏi đã chọn", disabled=not api_ready()):
            answer_row = by_id[selected_id]
            try:
                with st.spinner("Đang gọi LLM Judge…"):
                    judged = judge_answer(selected["question"], answer_row["actual_answer"], [ctx["text"] for ctx in answer_row.get("retrieved_contexts", [])])
                st.session_state.last_benchmark_judge = judged
            except Exception as exc:
                st.error(f"LLM Judge gặp lỗi: {exc}")
        judged = st.session_state.get("last_benchmark_judge")
        if judged:
            a, b, c, d = st.columns(4)
            a.metric("Tổng điểm Judge", f"{judged.get('score', '—')}/5")
            for column, name, label in zip((b, c, d), ("correctness", "relevance", "safety"), ("Chính xác", "Liên quan", "An toàn")):
                column.metric(label, f"{judged.get('sub_scores', {}).get(name, '—')}/5")
            st.write(judged.get("reasoning_vi", judged.get("verdict", "")))
    else:
        st.info("Hãy chạy benchmark để tạo câu trả lời trước khi chấm.")


with st.sidebar:
    page = st.radio("Không gian làm việc", ["Trò chuyện", "Đánh giá"], label_visibility="collapsed")
    st.divider()
    st.markdown("**Lab 14**  \nĐánh giá & đo chuẩn AI")
    st.caption("Hỗ trợ OrbitTech · bộ tài liệu giả lập")

if page == "Trò chuyện":
    chat_page()
else:
    benchmark_page()
