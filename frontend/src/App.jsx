
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
  Download,
  RotateCcw,
  CheckCircle2,
  AlertCircle,
} from "lucide-react";
import "./App.css";

const OUTPUT_FORMATS = [
  {
    id: "searchable_pdf",
    title: "Searchable PDF",
    description:
      "Preserve the original pages while adding selectable, searchable text.",
    icon: FileSearch,
    recommended: true,
  },
  {
    id: "simple_pdf",
    title: "Simple PDF",
    description:
      "Create a clean document using the extracted text only.",
    icon: File,
    recommended: false,
  },
  {
    id: "text",
    title: "Text document",
    description:
      "Download the extracted content as an editable TXT file.",
    icon: FileText,
    recommended: false,
  },
];

const DOWNLOAD_FORMATS = [
  { id: "searchable", title: "Searchable PDF", extension: "searchable.pdf" },
  { id: "clean", title: "Simple PDF", extension: "simple.pdf" },
  { id: "text", title: "Text document", extension: "txt" },
];

function App() {
  const fileInput = useRef(null);

  const [selectedFile, setSelectedFile] = useState(null);
  const [outputFormat, setOutputFormat] = useState("searchable_pdf");
  const [isDragging, setIsDragging] = useState(false);
  const [message, setMessage] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState("");

  const [documentData, setDocumentData] = useState(null);
  const [correctionData, setCorrectionData] = useState(null);
  const [isReviewing, setIsReviewing] = useState(false);
  const [reviewMessage, setReviewMessage] = useState("");

  async function getErrorMessage(response) {
    try {
      const data = await response.json();
      return data.detail || "Something went wrong.";
    } catch {
      return "Something went wrong.";
    }
  }

  async function waitForJob(jobId) {
    const maxAttempts = 600; // 30 minutes, polling every 3 seconds

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

      await new Promise((resolve) => setTimeout(resolve, 3000));
    }

    throw new Error(
      "Processing took longer than 30 minutes. Your document may still be processing."
    );
  }

  async function fetchDocumentResults(documentId, includeCorrections = true) {
    const jsonPromise = fetch(
      `/api/documents/${documentId}/download?type=json`
    );

    const correctionsPromise = includeCorrections
      ? fetch(`/api/documents/${documentId}/corrections`)
      : Promise.resolve(null);

    const [jsonResponse, correctionsResponse] = await Promise.all([
      jsonPromise,
      correctionsPromise,
    ]);

    if (!jsonResponse.ok) {
      throw new Error(await getErrorMessage(jsonResponse));
    }

    if (includeCorrections && !correctionsResponse.ok) {
      throw new Error(await getErrorMessage(correctionsResponse));
    }

    const ocrJson = await jsonResponse.json();

    const corrections = includeCorrections
      ? await correctionsResponse.json()
      : null;

    setDocumentData(ocrJson);
    setCorrectionData(corrections);
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

  async function downloadOutput(type, extension) {
    if (!documentData?.document_id) return;

    try {
      setReviewMessage(`Preparing ${extension}...`);

      const response = await fetch(
        `/api/documents/${documentData.document_id}/download?type=${type}`
      );

      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }

      const blob = await response.blob();

      downloadFile(
        blob,
        `readable-${documentData.document_id}.${extension}`
      );

      setReviewMessage("Your download is ready.");
    } catch (error) {
      setReviewMessage(error.message || "Download failed.");
    }
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

      setProgress("Starting document processing...");

      const processResponse = await fetch(
        `/api/documents/${documentId}/process`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            output_format: outputFormat,
          }),
        }
      );

      if (!processResponse.ok) {
        throw new Error(await getErrorMessage(processResponse));
      }

      const processData = await processResponse.json();

      setProgress(
        outputFormat === "searchable_pdf"
          ? "Running OCR and adding a searchable text layer to your original PDF..."
          : "Extracting text from your document..."
      );

      await waitForJob(processData.job_id);

      setProgress(
        outputFormat === "searchable_pdf"
          ? "Preparing your searchable PDF and results..."
          : "Preparing your results..."
      );

      if (outputFormat === "searchable_pdf") {
        setDocumentData({
          document_id: documentId,
          pages: [],
          original_filename: selectedFile.name,
          original_type: selectedFile.type,
        });

        setCorrectionData(null);
      } else {
        await fetchDocumentResults(documentId, true);

        setDocumentData((current) => ({
          ...current,
          original_filename: selectedFile.name,
          original_type: selectedFile.type,
        }));
      }
    } catch (error) {
      setProgress("");
      setMessage(error.message || "Something went wrong.");
    } finally {
      setIsProcessing(false);
      setProgress("");
    }
  }

  async function handleCorrection(correctionId, decision) {
    if (!documentData?.document_id || isReviewing) return;

    try {
      setIsReviewing(true);
      setReviewMessage(
        decision === "accepted"
          ? "Applying correction..."
          : "Saving your decision..."
      );

      const response = await fetch(
        `/api/documents/${documentData.document_id}/corrections/${correctionId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision }),
        }
      );

      if (!response.ok) {
        throw new Error(await getErrorMessage(response));
      }

      const result = await response.json();

      if (result.job_id) {
        setReviewMessage("Rebuilding your corrected document...");
        await waitForJob(result.job_id);
      }

      await fetchDocumentResults(documentData.document_id);
      setReviewMessage("Your review decision has been saved.");
    } catch (error) {
      setReviewMessage(error.message || "Could not save your decision.");
    } finally {
      setIsReviewing(false);
    }
  }

  function startNewDocument() {
    setDocumentData(null);
    setCorrectionData(null);
    setSelectedFile(null);
    setMessage("");
    setReviewMessage("");
    setProgress("");
    setOutputFormat("searchable_pdf");

    if (fileInput.current) {
      fileInput.current.value = "";
    }
  }

  const isPdf = documentData?.original_type === "application/pdf";

  if (documentData) {
    const statistics = correctionData?.correction_statistics || {};
    const corrections = correctionData?.corrections || [];
    const pages = documentData.pages || [];

    return (
      <div className="home-shell">
        <header className="site-header">
          <a href="/" className="brand" onClick={(event) => {
            event.preventDefault();
            startNewDocument();
          }}>
            <span className="brand-mark">
              <ScanText size={22} />
            </span>
            <span>readablePDF</span>
          </a>

          <div className="header-note">
            <ShieldCheck size={16} />
            <span>Searchable PDF OCR</span>
          </div>
        </header>

        <main className="results-main">
          <div className="results-topline">
            <button className="back-button" onClick={startNewDocument}>
              <RotateCcw size={16} />
              New document
            </button>
            <span className="eyebrow">PROCESSING COMPLETE</span>
          </div>

          <section className="results-heading">
            <div className="success-mark">
              <CheckCircle2 size={27} />
            </div>
            <h1>
              {isPdf ? (
                <>Your scanned PDF is <span>searchable again.</span></>
              ) : (
                <>Your extracted text is <span>ready.</span></>
              )}
            </h1>
            <p>
              {isPdf
                ? "The original pages are preserved with a selectable, searchable OCR text layer. Download the searchable PDF, then review the extracted text or suggested corrections."
                : "Review the extracted content and suggested corrections, or download it as a Simple PDF or editable text document."}
            </p>
            <div className="document-name">
              <FileText size={17} />
              <span>
                {documentData.original_filename || documentData.document_id}
              </span>
            </div>
          </section>

          <section className="results-section download-section">
            <div className="results-section-heading">
              <div>
                <span className="step-number">01</span>
                <h2>{isPdf ? "Your searchable PDF" : "Download your document"}</h2>
              </div>
              {isPdf && <span className="section-note">Main output</span>}
            </div>

            <div className="download-list">
              {DOWNLOAD_FORMATS
                .filter((format) => {
                  if (outputFormat === "searchable_pdf") {
                    return format.id === "searchable";
                  }
                  if (outputFormat === "simple_pdf") {
                    return format.id === "clean";
                  }
                  return format.id === "text";
                })
                .map((format) => {
                const unavailable = format.id === "searchable" && !isPdf;
                const isPrimary = format.id === "searchable";
                const Icon =
                  isPrimary
                    ? FileSearch
                    : format.id === "clean"
                      ? File
                      : FileText;

                return (
                  <div
                    className={`download-option ${isPrimary ? "primary-download-option" : ""}`}
                    key={format.id}
                  >
                    <div className="download-icon">
                      <Icon size={21} />
                    </div>
                    <div className="download-info">
                      <strong>{format.title}</strong>
                      <span>
                        {unavailable
                          ? "Only available for PDF uploads"
                          : isPrimary
                            ? "Preserves the original pages with selectable, searchable text."
                            : format.id === "clean"
                              ? "A clean document made from the extracted text only."
                              : "Editable extracted text in TXT format."}
                      </span>
                    </div>
                    <button
                      className={`download-button ${isPrimary ? "primary-download-button" : ""}`}
                      disabled={unavailable}
                      onClick={() =>
                        downloadOutput(format.id, format.extension)
                      }
                      aria-label={`Download ${format.title}`}
                    >
                      <Download size={17} />
                      {isPrimary && <span>Download PDF</span>}
                    </button>
                  </div>
                );
              })}
            </div>
            {isPdf && (
              <p className="highlight-note">
                You can select, copy, and search text in the PDF. Highlighting
                depends on the PDF viewer.
              </p>
            )}
          </section>

          {outputFormat !== "searchable_pdf" && (
            <section className="statistics-grid">
              <div className="stat-card">
                <span className="stat-label">Pages processed</span>
                <strong>{pages.length}</strong>
              </div>
              <div className="stat-card">
                <span className="stat-label">Corrections found</span>
                <strong>{statistics.total ?? corrections.length}</strong>
              </div>
              <div className="stat-card">
                <span className="stat-label">Accepted</span>
                <strong>{statistics.accepted ?? 0}</strong>
              </div>
              <div className="stat-card">
                <span className="stat-label">Pending review</span>
                <strong>{statistics.pending_review ?? 0}</strong>
              </div>
            </section>
          )}

          {outputFormat !== "searchable_pdf" && (
            <section className="results-section">
              <div className="results-section-heading">
                <div>
                  <span className="step-number">03</span>
                  <h2>Correction review</h2>
                </div>
                <span className="section-note">
                  {corrections.length} suggestions
                </span>
              </div>

              {corrections.length === 0 ? (
                <div className="empty-review">
                  <CheckCircle2 size={22} />
                  <div>
                    <strong>No correction suggestions</strong>
                    <p>
                      The OCR engine did not identify any words that need
                      manual review.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="correction-list">
                  {corrections.map((correction) => {
                    const pending = !correction.decision;
                    const accepted = correction.decision === "accepted";
                    const rejected = correction.decision === "rejected";

                    return (
                      <article
                        className="correction-card"
                        key={correction.id}
                      >
                        <div className="correction-card-top">
                          <span className="correction-location">
                            Page {correction.page}
                          </span>
                          <span
                            className={`correction-status ${
                              accepted
                                ? "accepted"
                                : rejected
                                  ? "rejected"
                                  : "pending"
                            }`}
                          >
                            {accepted
                              ? "Accepted"
                              : rejected
                                ? "Rejected"
                                : "Needs review"}
                          </span>
                        </div>

                        <div className="correction-comparison">
                          <div>
                            <span>Original</span>
                            <strong>{correction.original}</strong>
                          </div>
                          <ArrowRight size={17} />
                          <div>
                            <span>Suggested</span>
                            <strong>{correction.corrected}</strong>
                          </div>
                        </div>

                        {(correction.previous || correction.following) && (
                          <p className="correction-context">
                            Context:{" "}
                            {[correction.previous, correction.original, correction.following]
                              .filter(Boolean)
                              .join(" ")}
                          </p>
                        )}

                        {pending && (
                          <div className="correction-actions">
                            <button
                              className="accept-button"
                              disabled={isReviewing}
                              onClick={() =>
                                handleCorrection(correction.id, "accepted")
                              }
                            >
                              <Check size={15} />
                              Accept
                            </button>
                            <button
                              className="reject-button"
                              disabled={isReviewing}
                              onClick={() =>
                                handleCorrection(correction.id, "rejected")
                              }
                            >
                              <X size={15} />
                              Reject
                            </button>
                          </div>
                        )}
                      </article>
                    );
                  })}
                </div>
              )}

              {reviewMessage && (
                <p className="review-message" role="status">
                  {reviewMessage}
                </p>
              )}
            </section>
          )}

          <div className="results-footer-note">
            <ShieldCheck size={16} />
            <span>Your original uploaded document remains unchanged.</span>
          </div>
        </main>

        <footer className="site-footer">
          <span>readablePDF</span>
          <span>Making scanned PDFs searchable.</span>
        </footer>
      </div>
    );
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
          <span>Searchable PDF OCR</span>
        </div>
      </header>

      <main className="home-main">
        <section className="hero-section">
          <p className="eyebrow">OCR FOR SCANNED DOCUMENTS</p>

          <h1>
            Make scanned PDFs
            <br />
            <span>selectable again.</span>
          </h1>

          <p className="hero-description">
            Turn scanned pages into searchable PDFs. Select sentences, copy
            passages, and highlight text while keeping the original document&apos;s
            appearance.
          </p>
          <p className="hero-note">
            Highlighting is handled by your PDF viewer.
          </p>
        </section>

        <form className="upload-workspace" onSubmit={handleSubmit}>
          <div className="section-heading">
            <div>
              <span className="step-number">01</span>
              <h2>Upload your document</h2>
            </div>
            <span className="section-note">Scanned PDF recommended</span>
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
                  Scanned PDF recommended · PNG/JPG also supported
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
                    } ${
                      format.recommended ? "primary-format-option" : ""
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
                            Main output
                          </span>
                        )}
                      </div>
                      <p>
                        {format.id === "searchable_pdf" &&
                        selectedFile &&
                        selectedFile.type !== "application/pdf"
                          ? "Available for PDF uploads only."
                          : format.description}
                      </p>
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
              {isProcessing
                ? "Processing..."
                : outputFormat === "searchable_pdf"
                  ? "Create searchable PDF"
                  : outputFormat === "simple_pdf"
                    ? "Create Simple PDF"
                    : "Extract text"}
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
              <h3>Add a text layer</h3>
              <p>
                OCR adds selectable, searchable text while preserving the
                original PDF pages.
              </p>
            </div>

            <div>
              <span>03</span>
              <h3>Use your PDF</h3>
              <p>
                Select, copy, and search text. Highlighting depends on your
                PDF viewer.
              </p>
            </div>
          </div>
        </section>

        <section className="about-section" id="about">
          <h2>Why searchable PDFs?</h2>
          <p>
            Scanned PDFs often contain images of text rather than actual text.
            readablePDF uses OCR to add a text layer, allowing you to select,
            copy, search and work with the original document without changing
            its appearance.
          </p>
        </section>
      </main>

      <footer className="site-footer">
        <span>readablePDF</span>
        <span>Making scanned PDFs searchable.</span>
      </footer>
    </div>
  );
}

export default App;
