# Deep Research Agent

A Python based Deep Research Agent built for the Sarvam AI Assignment.

The system performs autonomous web research, retrieves webpage content, selects relevant context, and generates citation-grounded responses using LLM based synthesis.

Built entirely without LangChain, LangGraph, CrewAI, LlamaIndex, or other agent orchestration frameworks.

Note: For this submission, Groq + Tavily were primarily used due to free-tier availability and rate limit considerations. But the architecture is designed to be provider flexible and can be extended to support multiple LLM and search providers (Groq, OpenAI, Gemini, Tavily, Serper). 

---

## Features

- Web search using Tavily API
- Extensible provider architecture for Groq/OpenAI/Gemini and Tavily/Serper
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

## Run Evaluation Harness

```bash
python eval_harness.py
```

The generated evaluation results are stored in:

```bash
evaluation_report.md
```

---

## Run the Application

Open a new terminal after evaluation setup and run:

```bash
python -m streamlit run app.py
```
