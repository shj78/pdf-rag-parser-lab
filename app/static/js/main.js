let currentDocumentId = null;

function formatTrace(trace = []) {
  if (!Array.isArray(trace) || trace.length === 0) {
    return "기록된 처리 과정이 없습니다.";
  }

  return trace
    .map((item, index) => {
      const extra = Object.entries(item)
        .filter(([key, value]) => {
          return !["step", "detail", "elapsed_ms"].includes(key) && value !== null && value !== "";
        })
        .map(([key, value]) => `  - ${key}: ${value}`)
        .join("\n");

      const header = `${index + 1}. [${item.elapsed_ms}ms] ${item.step}`;
      return extra
        ? `${header}\n   ${item.detail}\n${extra}`
        : `${header}\n   ${item.detail}`;
    })
    .join("\n\n");
}

async function uploadDocument() {
  const fileInput = document.getElementById("file");
  const uploadButton = document.getElementById("uploadButton");
  const uploadSpinner = document.getElementById("uploadSpinner");
  const uploadButtonText = uploadButton.querySelector(".btn-text");

  const file = fileInput.files[0];
  if (!file) {
    alert("파일을 선택해주세요.");
    return;
  }

  uploadButton.disabled = true;
  uploadSpinner.classList.remove("hidden");
  uploadButtonText.classList.add("hidden");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const uploadResponse = await fetch("/documents/", {
      method: "POST",
      body: formData,
    });

    if (!uploadResponse.ok) {
      const errorData = await uploadResponse
        .json()
        .catch(() => ({ detail: uploadResponse.statusText }));
      throw new Error(
        `문서 처리 실패: ${errorData.detail || uploadResponse.status}`
      );
    }

    const uploadData = await uploadResponse.json();
    currentDocumentId = uploadData.document_id;

    document.getElementById("qaDocumentIdDisplay").textContent =
      currentDocumentId;
    document.getElementById("qaFileNameDisplay").textContent = file.name;

    document.getElementById("upload-section").classList.add("hidden");
    document.getElementById("qa-section").classList.remove("hidden");
    document.getElementById("askButton").disabled = false;
    document.getElementById("resetSessionButton").disabled = false;
  } catch (error) {
    console.error("Error:", error);
    alert(`오류 발생: ${error.message}`);
  } finally {
    uploadSpinner.classList.add("hidden");
    uploadButtonText.classList.remove("hidden");
    uploadButton.disabled = false;
  }
}

async function askQuestion() {
  const questionInput = document.getElementById("question");
  const question = questionInput.value;
  const askButton = document.getElementById("askButton");
  const answerDiv = document.getElementById("answer");
  const loadingSpinner = document.getElementById("loadingSpinner");
  const answerContainer = document.getElementById("answer-container");
  const askButtonText = askButton.querySelector(".btn-text");
  const tracePanel = document.getElementById("trace-panel");
  const traceMeta = document.getElementById("trace-meta");
  const traceOutput = document.getElementById("trace-output");

  if (!question) {
    alert("질문을 입력해주세요.");
    return;
  }

  if (!currentDocumentId) {
    alert("문서를 먼저 업로드해주세요.");
    return;
  }

  try {
    askButton.disabled = true;
    loadingSpinner.classList.remove("hidden");
    askButtonText.classList.add("hidden");

    answerDiv.textContent = "";
    traceMeta.textContent = "";
    traceOutput.textContent = "";
    answerContainer.classList.remove("hidden");
    answerDiv.classList.add("hidden");
    tracePanel.classList.add("hidden");

    const response = await fetch("/qa", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query: question,
        document_id: currentDocumentId,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    answerDiv.textContent = data.answer;
    traceMeta.textContent = `trace_id: ${data.trace_id || "-"}\ntrace_file: ${data.trace_file || "-"}`;
    traceOutput.textContent = formatTrace(data.debug_trace);
    tracePanel.classList.remove("hidden");
    console.group("RAG Trace");
    console.log(data.debug_trace || []);
    console.groupEnd();
  } catch (error) {
    console.error("Error:", error);
    answerDiv.textContent = `오류 발생: ${error.message}`;
    traceMeta.textContent = "";
    traceOutput.textContent = "";
    tracePanel.classList.add("hidden");
  } finally {
    askButton.disabled = false;
    loadingSpinner.classList.add("hidden");
    askButtonText.classList.remove("hidden");
    answerDiv.classList.remove("hidden");
  }
}

async function resetSession() {
  if (!currentDocumentId) {
    alert("초기화할 세션이 없습니다.");
    return;
  }

  const askButton = document.getElementById("askButton");
  const resetButton = document.getElementById("resetSessionButton");

  try {
    askButton.disabled = true;
    resetButton.disabled = true;

    const response = await fetch("/qa/reset", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        document_id: currentDocumentId,
      }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    document.getElementById("question").value = "";
    document.getElementById("answer").textContent = "";
    document.getElementById("trace-meta").textContent = "";
    document.getElementById("trace-output").textContent = "";
    document.getElementById("trace-panel").classList.add("hidden");
    document.getElementById("answer-container").classList.add("hidden");
    alert("세션이 종료되었습니다. 새로운 첫 질문부터 시작할 수 있습니다.");
  } catch (error) {
    console.error("Error:", error);
    alert(`세션 종료 오류: ${error.message}`);
  } finally {
    askButton.disabled = false;
    resetButton.disabled = false;
  }
}

document.addEventListener("DOMContentLoaded", function () {
  const uploadButton = document.getElementById("uploadButton");
  uploadButton.addEventListener("click", uploadDocument);

  const askButton = document.getElementById("askButton");
  askButton.addEventListener("click", askQuestion);

  const resetSessionButton = document.getElementById("resetSessionButton");
  resetSessionButton.addEventListener("click", resetSession);

  const fileInput = document.getElementById("file");
  const fileNameSpan = document.getElementById("fileName");

  fileInput.addEventListener("change", function () {
    const uploadButton = document.getElementById("uploadButton");
    if (fileInput.files.length > 0) {
      fileNameSpan.textContent = fileInput.files[0].name;
      uploadButton.classList.remove("hidden");
    } else {
      fileNameSpan.textContent = "선택된 파일 없음";
      uploadButton.classList.add("hidden");
    }
  });

  const backButton = document.getElementById("backButton");
  backButton.addEventListener("click", function () {
    // Hide QA section, show Upload section
    document.getElementById("qa-section").classList.add("hidden");
    document.getElementById("upload-section").classList.remove("hidden");

    // Reset state
    currentDocumentId = null;
    document.getElementById("question").value = "";
    document.getElementById("answer").textContent = "";
    document.getElementById("trace-meta").textContent = "";
    document.getElementById("trace-output").textContent = "";
    document.getElementById("trace-panel").classList.add("hidden");
    document.getElementById("answer-container").classList.add("hidden");
    document.getElementById("askButton").disabled = true;
    document.getElementById("resetSessionButton").disabled = true;
    document.getElementById("qaFileNameDisplay").textContent = "";

    // Reset file input
    const fileInput = document.getElementById("file");
    const fileNameSpan = document.getElementById("fileName");
    fileInput.value = "";
    fileNameSpan.textContent = "선택된 파일 없음";
    document.getElementById("uploadButton").classList.add("hidden");
  });
});
