# Deep Research Agent

A Python based Deep Research Agent for web research and citation grounded response generation.

The system performs autonomous web research, retrieves webpage content, selects relevant context, and generates citation grounded responses using LLM based synthesis.

Built entirely without LangChain, LangGraph, CrewAI, LlamaIndex, or other agent orchestration frameworks.

Note: For this submission, Groq + Tavily were primarily used due to free tier availability and rate limit considerations. The architecture is designed to be extensible and provider flexible, making it easier to integrate additional LLM and search providers such as OpenAI, Gemini, and Serper in future iterations.

---

## Features

- Built using Python, Groq API, and Tavily API
- Provider flexible architecture designed for future OpenAI/Gemini and Serper integration
- Citation grounded answer generation
- Async orchestration using asyncio
- Session and conversation persistence using SQLite
- Context selection and summarization
- Streaming intermediate progress updates
- Streamlit based UI
- Evaluation harness with benchmark dataset
- Conflict handling and uncertainty detection
- Multi turn conversational memory

---

## Tech Stack

- Python
- Groq API
- Tavily API
- Streamlit
- SQLite
- httpx
- BeautifulSoup4

---

## Project Structure

```bash
.
├── app.py
├── agent_engine.py
├── research_tools.py
├── models.py
├── eval_harness.py
├── evaluation_report.md
├── requirements.txt
```
## Setup Instructions

### 1. Create Virtual Environment

```bash
python -m venv .venv
```

### 2. Activate Environment (Windows PowerShell)

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Environment Variables

```powershell
$env:GROQ_API_KEY="YOUR_GROQ_API_KEY"
$env:TAVILY_API_KEY="YOUR_TAVILY_API_KEY"
```


---

## Initialize Database

```bash
python models.py
```



---

## Run Evaluation Harness

```bash
python eval_harness.py
```

The generated evaluation results are stored in:

```bash
evaluation_report.md
```

The submitted evaluation_report.md file was generated directly by running eval_harness.py .

---
## Run the Application



```bash
python -m streamlit run app.py
```
