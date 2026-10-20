export const PDF_LABEL_ADVANCED_STORAGE_KEY = "fba_pdf_label_advanced_options";

export const MAX_CUSTOM_TEXT_LEN = 80;

export type PdfLabelDetectDpi = 120 | 200 | 300;

export type PdfLabelAdvancedOptions = {
  paddingMm: number;
  ignoreTopMm: number;
  ignoreBottomMm: number;
  detectDpi: PdfLabelDetectDpi;
  customText: string;
};

export const DEFAULT_PDF_LABEL_ADVANCED_OPTIONS: PdfLabelAdvancedOptions = {
  paddingMm: 1.0,
  ignoreTopMm: 0,
  ignoreBottomMm: 0,
  detectDpi: 120,
  customText: "",
};

function clampNonNeg(value: unknown, fallback: number, max = 50): number {
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n) || n < 0) return fallback;
  return Math.min(n, max);
}

function parseDetectDpi(value: unknown): PdfLabelDetectDpi {
  const n = typeof value === "number" ? value : Number(value);
  if (n === 200 || n === 300) return n;
  return 120;
}

function parseCustomText(value: unknown): string {
  if (typeof value !== "string") return "";
  return value.trim().slice(0, MAX_CUSTOM_TEXT_LEN);
}

export function loadPdfLabelAdvancedOptions(): PdfLabelAdvancedOptions {
  if (typeof window === "undefined") return { ...DEFAULT_PDF_LABEL_ADVANCED_OPTIONS };
  try {
    const raw = localStorage.getItem(PDF_LABEL_ADVANCED_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PDF_LABEL_ADVANCED_OPTIONS };
    const parsed = JSON.parse(raw) as Partial<PdfLabelAdvancedOptions>;
    return {
      paddingMm: clampNonNeg(parsed.paddingMm, DEFAULT_PDF_LABEL_ADVANCED_OPTIONS.paddingMm),
      ignoreTopMm: clampNonNeg(parsed.ignoreTopMm, DEFAULT_PDF_LABEL_ADVANCED_OPTIONS.ignoreTopMm),
      ignoreBottomMm: clampNonNeg(
        parsed.ignoreBottomMm,
        DEFAULT_PDF_LABEL_ADVANCED_OPTIONS.ignoreBottomMm,
      ),
      detectDpi: parseDetectDpi(parsed.detectDpi),
      customText: parseCustomText(parsed.customText),
    };
  } catch {
    return { ...DEFAULT_PDF_LABEL_ADVANCED_OPTIONS };
  }
}

export function savePdfLabelAdvancedOptions(options: PdfLabelAdvancedOptions): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(PDF_LABEL_ADVANCED_STORAGE_KEY, JSON.stringify(options));
}

export function advancedOptionsToApiPayload(options: PdfLabelAdvancedOptions) {
  const payload: Record<string, string | number> = {
    padding_mm: options.paddingMm,
    ignore_top_mm: options.ignoreTopMm,
    ignore_bottom_mm: options.ignoreBottomMm,
    detect_dpi: options.detectDpi,
  };
  const text = options.customText.trim();
  if (text) {
    payload.custom_text = text.slice(0, MAX_CUSTOM_TEXT_LEN);
  }
  return payload;
}
