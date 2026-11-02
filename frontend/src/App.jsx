
import { useRef, useState } from "react";
import {
  ScanText,
  Upload,
  FileText,
  FileSearch,
  File,
  Check,
  ArrowRight,
  X,
  ShieldCheck,
  BookOpen,
} from "lucide-react";
import "./App.css";

const OUTPUT_FORMATS = [
  {
    id: "searchable_pdf",
    title: "Searchable PDF",
    description:
      "Keep the original page appearance while adding selectable and searchable text.",
    icon: FileSearch,
    recommended: true,
  },
  {
    id: "simple_pdf",
    title: "Simple PDF",
    description:
      "Create a clean, readable PDF reconstructed from the extracted text.",
    icon: File,
    recommended: false,
  },
  {
    id: "text",
    title: "Text document",
    description:
      "Extract the document's text into a simple editable .txt file.",
    icon: FileText,
    recommended: false,
  },
];

function App() {
  const fileInput = useRef(null);

  const [selectedFile, setSelectedFile] = useState(null);
  const [outputFormat, setOutputFormat] = useState("searchable_pdf");
  const [isDragging, setIsDragging] = useState(false);
  const [message, setMessage] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState("");

  async function getErrorMessage(response) {
    try {
      const data = await response.json();
      return data.detail || "Something went wrong.";
    } catch {
      return "Something went wrong.";
    }
  }

  async function waitForJob(jobId) {
    const maxAttempts = 180;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const response = await fetch(`/api/jobs/${jobId}`);

      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }

      const job = await response.json();

      if (job.status === "finished") {
        return job.result;
      }

      if (job.status === "failed") {
        throw new Error(job.error || "Document processing failed.");
      }

      await new Promise((resolve) => setTimeout(resolve, 1000));
    }

    throw new Error("Processing timed out. Please try again.");
  }

  function downloadFile(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = filename;

    document.body.appendChild(link);
    link.click();
    link.remove();

    URL.revokeObjectURL(url);
  }

  function handleFile(file) {
    setMessage("");

    if (!file) return;

    const allowedTypes = [
      "application/pdf",
      "image/png",
      "image/jpeg",
    ];

    if (!allowedTypes.includes(file.type)) {
      setMessage("Please select a PDF, PNG or JPG file.");
      return;
    }

    setSelectedFile(file);
  }

  function handleDrop(event) {
    event.preventDefault();
    setIsDragging(false);
    handleFile(event.dataTransfer.files[0]);
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (!selectedFile) {
      setMessage("Please select a document first.");
      return;
    }

    if (
      outputFormat === "searchable_pdf" &&
      selectedFile.type !== "application/pdf"
    ) {
      setMessage(
        "Searchable PDF is currently available for PDF uploads only."
      );
      return;
    }

    try {
      setIsProcessing(true);
      setMessage("");
      setProgress("Uploading your document...");

      // 1. Upload document.
      const formData = new FormData();
      formData.append("file", selectedFile);

      const uploadResponse = await fetch("/api/documents/upload", {
        method: "POST",
        body: formData,
      });

      if (!uploadResponse.ok) {
        throw new Error(await getErrorMessage(uploadResponse));
      }

      const uploadedDocument = await uploadResponse.json();
      const documentId = uploadedDocument.document_id;

      // 2. Start processing.
      setProgress("Starting document processing...");

      const processResponse = await fetch(
        `/api/documents/${documentId}/process`,
        {
          method: "POST",
        }
      );

      if (!processResponse.ok) {
        throw new Error(await getErrorMessage(processResponse));
      }

      const processData = await processResponse.json();

      // 3. Wait for OCR processing.
      setProgress("Extracting text from your document...");

      await waitForJob(processData.job_id);

      // 4. Download selected output.
      setProgress("Preparing your download...");

      const downloadTypes = {
        searchable_pdf: "searchable",
        simple_pdf: "clean",
        text: "text",
      };

      const downloadType = downloadTypes[outputFormat];

      const downloadResponse = await fetch(
        `/api/documents/${documentId}/download?type=${downloadType}`
      );

      if (!downloadResponse.ok) {
        throw new Error(await getErrorMessage(downloadResponse));
      }

      const blob = await downloadResponse.blob();

      const extensions = {
        searchable_pdf: "searchable.pdf",
        simple_pdf: "simple.pdf",
        text: "txt",
      };

      downloadFile(
        blob,
        `readable-${documentId}.${extensions[outputFormat]}`
      );

      setProgress("");
      setMessage("Your document has been processed and downloaded successfully.");
    } catch (error) {
      setProgress("");
      setMessage(error.message || "Something went wrong.");
    } finally {
      setIsProcessing(false);
    }
  }

  return (
    <div className="home-shell">
      <header className="site-header">
        <a href="/" className="brand">
          <span className="brand-mark">
            <ScanText size={22} />
          </span>
          <span>readablePDF</span>
        </a>

        <nav className="header-nav">
          <a href="#how-it-works">How it works</a>
          <a href="#about">About</a>
        </nav>

        <div className="header-note">
          <ShieldCheck size={16} />
          <span>Document accessibility</span>
        </div>
      </header>

      <main className="home-main">
        <section className="hero-section">
          <p className="eyebrow">A BETTER WAY TO READ DOCUMENTS</p>

          <h1>
            Make your documents
            <br />
            <span>readable again.</span>
          </h1>

          <p className="hero-description">
            Turn scanned documents into searchable, accessible and
            easy-to-read files. Upload a document and choose how you
            want to read it.
          </p>
        </section>

        <form className="upload-workspace" onSubmit={handleSubmit}>
          <div className="section-heading">
            <div>
              <span className="step-number">01</span>
              <h2>Upload your document</h2>
            </div>
            <span className="section-note">PDF or image</span>
          </div>

          <div
            className={`drop-zone ${isDragging ? "dragging" : ""} ${
              selectedFile ? "has-file" : ""
            }`}
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInput.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                fileInput.current?.click();
              }
            }}
          >
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
              hidden
              onChange={(event) => handleFile(event.target.files[0])}
            />

            {selectedFile ? (
              <>
                <div className="upload-icon">
                  <FileText size={25} />
                </div>

                <div className="selected-file">
                  <strong>{selectedFile.name}</strong>
                  <span>
                    {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                  </span>
                </div>

                <button
                  type="button"
                  className="remove-file"
                  aria-label="Remove selected file"
                  onClick={(event) => {
                    event.stopPropagation();
                    setSelectedFile(null);
                    setMessage("");
                    if (fileInput.current) {
                      fileInput.current.value = "";
                    }
                  }}
                >
                  <X size={18} />
                </button>
              </>
            ) : (
              <>
                <div className="upload-icon">
                  <Upload size={25} strokeWidth={1.6} />
                </div>

                <h3>Drop your document here</h3>
                <p>or browse files from your device</p>

                <span className="browse-button">Choose a file</span>

                <span className="file-types">
                  PDF, PNG or JPG
                </span>
              </>
            )}
          </div>

          <div className="format-section">
            <div className="section-heading">
              <div>
                <span className="step-number">02</span>
                <h2>Choose your output format</h2>
              </div>
            </div>

            <div className="format-list">
              {OUTPUT_FORMATS.map((format) => {
                const Icon = format.icon;
                const isSelected = outputFormat === format.id;

                return (
                  <button
                    type="button"
                    key={format.id}
                    className={`format-option ${
                      isSelected ? "selected" : ""
                    }`}
                    onClick={() => setOutputFormat(format.id)}
                  >
                    <div className="format-icon">
                      <Icon size={23} strokeWidth={1.6} />
                    </div>

                    <div className="format-content">
                      <div className="format-title">
                        <strong>{format.title}</strong>
                        {format.recommended && (
                          <span className="recommended">
                            Recommended
                          </span>
                        )}
                      </div>
                      <p>{format.description}</p>
                    </div>

                    <span className="selection-indicator">
                      {isSelected && <Check size={14} />}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {message && (
            <div className="form-message" role="status">
              {message}
            </div>
          )}

          {progress && (
            <div className="form-message" role="status">
              {progress}
            </div>
          )}

          <div className="submit-section">
            <div className="privacy-note">
              <ShieldCheck size={16} />
              <span>Your document is processed in your workspace.</span>
            </div>

            <button
              type="submit"
              className="process-button"
              disabled={!selectedFile || isProcessing}
            >
              {isProcessing ? "Processing..." : "Continue"}
              {!isProcessing && <ArrowRight size={17} />}
            </button>
          </div>
        </form>

        <section className="how-section" id="how-it-works">
          <div className="how-heading">
            <BookOpen size={19} />
            <h2>Simple by design.</h2>
          </div>

          <div className="how-grid">
            <div>
              <span>01</span>
              <h3>Upload</h3>
              <p>Choose a scanned PDF or image from your device.</p>
            </div>

            <div>
              <span>02</span>
              <h3>Process</h3>
              <p>Our OCR engine extracts text from your document.</p>
            </div>

            <div>
              <span>03</span>
              <h3>Download</h3>
              <p>Get your document in the format you selected.</p>
            </div>
          </div>
        </section>
      </main>

      <footer className="site-footer" id="about">
        <span>readablePDF</span>
        <span>Making scanned documents accessible.</span>
      </footer>
    </div>
  );
}

export default App;
