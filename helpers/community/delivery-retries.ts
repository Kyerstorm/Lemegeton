export interface DeliveryRetryPlan {
  attempts: number;
  status: "pending" | "failed";
  delayMinutes: number;
}

export function resolveDeliveryRetry(currentAttempts: number, baseDelayMinutes: number, maxAttempts = 8): DeliveryRetryPlan {
  if (!Number.isSafeInteger(currentAttempts) || currentAttempts < 0) {
    throw new RangeError("Delivery attempts must be a non-negative safe integer.");
  }
  if (!Number.isSafeInteger(baseDelayMinutes) || baseDelayMinutes < 1) {
    throw new RangeError("Delivery retry delay must be a positive integer number of minutes.");
  }
  if (!Number.isSafeInteger(maxAttempts) || maxAttempts < 1) {
    throw new RangeError("Delivery retry limit must be a positive safe integer.");
  }
  const attempts = currentAttempts + 1;
  return {
    attempts,
    status: attempts >= maxAttempts ? "failed" : "pending",
    delayMinutes: Math.min(attempts, 10) * baseDelayMinutes,
  };
}
