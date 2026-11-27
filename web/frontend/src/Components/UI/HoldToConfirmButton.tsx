"use client";

import {
  type ComponentPropsWithoutRef,
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { Icon } from "../Icons";

export type ConfirmationInput = "keyboard" | "pointer";
type HoldStatus = "confirmed" | "holding" | "idle";

type HoldToConfirmButtonProps = Omit<
  ComponentPropsWithoutRef<"button">,
  "children" | "onClick"
> & {
  children?: ReactNode;
  confirmedContent?: ReactNode;
  duration?: number;
  onConfirm: (input: ConfirmationInput) => void;
  resetAfter?: number;
};

export function HoldToConfirmButton({
  children = "Hold to confirm",
  className,
  confirmedContent,
  disabled,
  duration = 1600,
  onConfirm,
  resetAfter = 1800,
  ...buttonProps
}: HoldToConfirmButtonProps) {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const confirmTimerRef = useRef<number | null>(null);
  const resetTimerRef = useRef<number | null>(null);
  const activePointerIdRef = useRef<number | null>(null);
  const inputModeRef = useRef<ConfirmationInput>("pointer");
  const isHoldingRef = useRef(false);
  const [inputMode, setInputMode] = useState<ConfirmationInput | null>(null);
  const [status, setStatus] = useState<HoldStatus>("idle");

  const clearConfirmTimer = useCallback(() => {
    if (confirmTimerRef.current !== null) {
      window.clearTimeout(confirmTimerRef.current);
      confirmTimerRef.current = null;
    }
  }, []);

  const completeHold = useCallback(() => {
    if (!isHoldingRef.current) return;

    isHoldingRef.current = false;
    activePointerIdRef.current = null;
    clearConfirmTimer();
    setStatus("confirmed");
    onConfirm(inputModeRef.current);

    if (resetAfter > 0) {
      resetTimerRef.current = window.setTimeout(() => {
        setStatus("idle");
        resetTimerRef.current = null;
      }, resetAfter);
    }
  }, [clearConfirmTimer, onConfirm, resetAfter]);

  const cancelHold = useCallback(() => {
    if (!isHoldingRef.current) return;

    isHoldingRef.current = false;
    activePointerIdRef.current = null;
    clearConfirmTimer();
    setStatus("idle");
  }, [clearConfirmTimer]);

  const startHold = useCallback(
    (input: ConfirmationInput) => {
      if (disabled || status === "confirmed" || isHoldingRef.current) return;

      if (resetTimerRef.current !== null) {
        window.clearTimeout(resetTimerRef.current);
        resetTimerRef.current = null;
      }

      inputModeRef.current = input;
      setInputMode(input);
      isHoldingRef.current = true;
      setStatus("holding");
      confirmTimerRef.current = window.setTimeout(completeHold, duration);
    },
    [completeHold, disabled, duration, status],
  );

  useEffect(() => {
    return () => {
      clearConfirmTimer();
      if (resetTimerRef.current !== null) {
        window.clearTimeout(resetTimerRef.current);
      }
    };
  }, [clearConfirmTimer]);

  useEffect(() => {
    if (disabled) cancelHold();
  }, [cancelHold, disabled]);

  function releasePointerCapture(pointerId: number) {
    const button = buttonRef.current;
    if (button?.hasPointerCapture(pointerId)) {
      button.releasePointerCapture(pointerId);
    }
  }

  function handlePointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (!event.isPrimary || event.button !== 0 || disabled) return;
    activePointerIdRef.current = event.pointerId;
    event.currentTarget.setPointerCapture(event.pointerId);
    startHold("pointer");
  }

  function handlePointerMove(event: PointerEvent<HTMLButtonElement>) {
    if (
      !isHoldingRef.current ||
      activePointerIdRef.current !== event.pointerId
    ) return;

    const rect = event.currentTarget.getBoundingClientRect();
    const padding = 8;
    const outside =
      event.clientX < rect.left - padding ||
      event.clientX > rect.right + padding ||
      event.clientY < rect.top - padding ||
      event.clientY > rect.bottom + padding;

    if (outside) {
      cancelHold();
      releasePointerCapture(event.pointerId);
    }
  }

  function handlePointerEnd(event: PointerEvent<HTMLButtonElement>) {
    if (activePointerIdRef.current !== event.pointerId) return;
    cancelHold();
    releasePointerCapture(event.pointerId);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.repeat || (event.key !== "Enter" && event.key !== " ")) return;
    event.preventDefault();
    startHold("keyboard");
  }

  function handleKeyUp(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    cancelHold();
  }

  const isConfirmed = status === "confirmed";
  const isHolding = status === "holding";
  const overlayStyle = {
    clipPath: isHolding ? "inset(0 0 0 0)" : "inset(0 100% 0 0)",
    transitionDuration:
      inputMode === "keyboard" ? "0ms" : isHolding ? `${duration}ms` : "180ms",
    transitionProperty: "clip-path",
    transitionTimingFunction: isHolding
      ? "linear"
      : "cubic-bezier(0.23, 1, 0.32, 1)",
  };

  return (
    <button
      {...buttonProps}
      aria-busy={isHolding}
      className={[
        "button",
        "hold-confirm-button",
        className,
        isHolding ? "is-holding" : "",
        isConfirmed ? "is-confirmed" : "",
      ].filter(Boolean).join(" ")}
      data-input={inputMode}
      disabled={disabled}
      onBlur={cancelHold}
      onKeyDown={handleKeyDown}
      onKeyUp={handleKeyUp}
      onLostPointerCapture={cancelHold}
      onPointerCancel={handlePointerEnd}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerEnd}
      ref={buttonRef}
      type="button"
    >
      {isConfirmed ? (
        <span className="hold-confirm-content">
          {confirmedContent ?? <><Icon name="check" size={14} /> Confirmed</>}
        </span>
      ) : (
        <>
          <span className="hold-confirm-content">{children}</span>
          <span
            aria-hidden="true"
            className="hold-confirm-overlay"
            style={overlayStyle}
          >
            {children}
          </span>
        </>
      )}
    </button>
  );
}
