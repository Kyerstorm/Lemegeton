import { useEffect, useRef } from "react";

const lockedDialogs = new Set<HTMLElement>();
let initialBodyOverflow: string | null = null;

export function useDialogFocus(
  open: boolean,
  initialFocusSelector?: string,
  onEscape?: () => void,
) {
  const dialogRef = useRef<HTMLElement | null>(null);
  const onEscapeRef = useRef(onEscape);

  useEffect(() => {
    onEscapeRef.current = onEscape;
  }, [onEscape]);

  useEffect(() => {
    if (!open) return;

    const dialog = dialogRef.current;
    if (!dialog) return;

    const previousFocus = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const getFocusableElements = () => Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ).filter(element => !element.closest("[hidden], [inert], [aria-hidden='true']"));

    const initialTarget = initialFocusSelector
      ? dialog.querySelector<HTMLElement>(initialFocusSelector)
      : null;
    const focusTarget = initialTarget && !initialTarget.hasAttribute("disabled")
      ? initialTarget
      : getFocusableElements()[0] ?? dialog;
    focusTarget.focus();

    const handleKeyDown = (event: KeyboardEvent) => {
      const activeDialogs = Array.from(
        document.querySelectorAll<HTMLElement>('[aria-modal="true"]'),
      );
      if (activeDialogs[activeDialogs.length - 1] !== dialog) return;

      if (event.key === "Escape") {
        event.preventDefault();
        onEscapeRef.current?.();
        return;
      }

      if (event.key !== "Tab") return;

      const elements = getFocusableElements();
      if (elements.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }

      const first = elements[0];
      const last = elements[elements.length - 1];
      const focusIsOutside = !dialog.contains(document.activeElement);

      if (event.shiftKey && (document.activeElement === first || focusIsOutside)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || focusIsOutside)) {
        event.preventDefault();
        first.focus();
      }
    };

    if (lockedDialogs.size === 0) {
      initialBodyOverflow = document.body.style.overflow;
    }
    lockedDialogs.add(dialog);
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      lockedDialogs.delete(dialog);
      if (lockedDialogs.size === 0) {
        document.body.style.overflow = initialBodyOverflow ?? "";
        initialBodyOverflow = null;
      }
      if (previousFocus?.isConnected) previousFocus.focus();
    };
  }, [open, initialFocusSelector]);

  return dialogRef;
}
