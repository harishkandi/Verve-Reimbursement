import { AlertTriangle, HelpCircle } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

interface Ask {
  title: string;
  text?: ReactNode;
  confirm: string;
  danger?: boolean;
  /** When set, the dialog asks for text (e.g. a reason) and resolves with it. */
  input?: { label: string; placeholder?: string; required?: boolean };
}

type Answer = { ok: false } | { ok: true; value: string };
const DialogContext = createContext<((ask: Ask) => Promise<Answer>) | null>(null);

/** Styled replacement for window.confirm / prompt. */
export function DialogProvider({ children }: { children: ReactNode }) {
  const [ask, setAsk] = useState<Ask | null>(null);
  const [value, setValue] = useState("");
  const resolver = useRef<(a: Answer) => void>();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  const open = useCallback((a: Ask) => {
    setValue("");
    setAsk(a);
    return new Promise<Answer>((resolve) => (resolver.current = resolve));
  }, []);

  const close = useCallback((answer: Answer) => {
    resolver.current?.(answer);
    setAsk(null);
  }, []);

  useEffect(() => {
    if (!ask) return;
    (ask.input ? inputRef.current : confirmRef.current)?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close({ ok: false });
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ask, close]);

  const blocked = Boolean(ask?.input?.required && !value.trim());

  return (
    <DialogContext.Provider value={open}>
      {children}
      {ask && (
        <div className="dialog-scrim" onMouseDown={(e) => e.target === e.currentTarget && close({ ok: false })}>
          <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!blocked) close({ ok: true, value: value.trim() });
              }}
            >
              <div className="body">
                <div className={`icon ${ask.danger ? "danger" : ""}`}>
                  {ask.danger ? <AlertTriangle size={19} /> : <HelpCircle size={19} />}
                </div>
                <div className="grow">
                  <h2 id="dialog-title">{ask.title}</h2>
                  {ask.text && <div className="text">{ask.text}</div>}
                  {ask.input && (
                    <label className="field" style={{ marginTop: 14 }}>
                      <span>{ask.input.label}</span>
                      <textarea ref={inputRef} className="input" placeholder={ask.input.placeholder} value={value}
                        onChange={(e) => setValue(e.target.value)} />
                    </label>
                  )}
                </div>
              </div>
              <div className="foot">
                <button type="button" className="btn" onClick={() => close({ ok: false })}>Cancel</button>
                <button ref={confirmRef} type="submit" className={`btn ${ask.danger ? "btn-danger-solid" : "btn-primary"}`} disabled={blocked}>
                  {ask.confirm}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </DialogContext.Provider>
  );
}

export function useDialog() {
  const ctx = useContext(DialogContext);
  if (!ctx) throw new Error("useDialog outside DialogProvider");
  return ctx;
}
