import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

type Tone = "success" | "error" | "info";
interface Toast {
  id: number;
  tone: Tone;
  text: string;
}

const ToastContext = createContext<((tone: Tone, text: string) => void) | null>(null);

/** Short confirmations shown bottom-right, so feedback appears where the user is, not at the top of a long page. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);

  const dismiss = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const show = useCallback(
    (tone: Tone, text: string) => {
      const id = next.current++;
      setToasts((t) => [...t.slice(-2), { id, tone, text }]);
      // Errors stay until dismissed; they usually need reading.
      if (tone !== "error") setTimeout(() => dismiss(id), 4500);
    },
    [dismiss],
  );

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className="toast" role={t.tone === "error" ? "alert" : "status"}>
            {t.tone === "success" ? <CheckCircle2 size={17} className="ok" /> : t.tone === "error" ? <AlertCircle size={17} className="err" /> : <Info size={17} className="inf" />}
            <div className="grow">{t.text}</div>
            <button aria-label="Dismiss" onClick={() => dismiss(t.id)}><X size={15} /></button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const show = useContext(ToastContext);
  if (!show) throw new Error("useToast outside ToastProvider");
  return {
    success: (text: string) => show("success", text),
    error: (text: string) => show("error", text),
    info: (text: string) => show("info", text),
  };
}
