import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { EmptyState } from "../../src/Components/Feedback/EmptyState";
import { ErrorState } from "../../src/Components/Feedback/ErrorState";
import { LoadingState } from "../../src/Components/Feedback/LoadingState";
import { SectionError } from "../../src/Components/Feedback/SectionError";

describe("EmptyState", () => {
  it("keeps an ordinary empty message out of the live status channel", () => {
    render(<EmptyState>No commands have been configured.</EmptyState>);

    expect(screen.getByText("No commands have been configured.")).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("announces the loading variant and renders its supporting skeleton", () => {
    const { container } = render(
      <EmptyState loading>Loading archive entries.</EmptyState>,
    );

    expect(screen.getByRole("status").textContent).toContain("Loading archive entries.");
    expect(container.querySelectorAll(".empty-skeleton .skeleton")).toHaveLength(2);
  });
});

describe("LoadingState", () => {
  it("announces its label and bounds the number of skeleton rows", () => {
    const { container } = render(<LoadingState label="Loading command settings" rows={20} />);

    expect(screen.getByRole("status", { name: "Loading command settings" })).toBeTruthy();
    expect(container.querySelectorAll(".loading-state-row")).toHaveLength(8);
  });

  it("renders at least one row when given a non-positive row count", () => {
    const { container } = render(<LoadingState label="Loading server settings" rows={0} />);

    expect(container.querySelectorAll(".loading-state-row")).toHaveLength(1);
  });
});

describe("ErrorState", () => {
  it("renders a recoverable error and invokes its retry action", () => {
    const onRetry = vi.fn();
    render(
      <ErrorState
        title="Command settings could not be loaded."
        description="Your saved settings have not been changed."
        onRetry={onRetry}
      />,
    );

    expect(screen.getByRole("alert").textContent).toContain("Command settings could not be loaded.");
    expect(screen.getByText("Your saved settings have not been changed.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open GitHub issue tracker" }).getAttribute("href")).toBe("/issues");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("does not render a retry control when no action is supplied", () => {
    render(<ErrorState title="Unavailable" description="Try again later." />);

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });
});

describe("SectionError", () => {
  it("maps offline failures to an actionable connection state", () => {
    const onRetry = vi.fn();
    render(<SectionError message="The network is unavailable." status={0} onRetry={onRetry} />);

    expect(screen.getByRole("alert").textContent).toContain("Connection unavailable.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("maps permission failures to the access recovery state", () => {
    render(<SectionError message="This server is not available to your account." status={403} onRetry={vi.fn()} />);

    expect(screen.getByRole("alert").textContent).toContain("Permission check failed.");
    expect(screen.getByRole("button", { name: "Refresh access" })).toBeTruthy();
  });

  it("maps rate limits and unavailable services to their distinct states", () => {
    const rateLimitRetry = vi.fn();
    const serviceRetry = vi.fn();

    const { rerender } = render(
      <SectionError message="Slow down." status={429} onRetry={rateLimitRetry} />,
    );
    expect(screen.getByRole("alert").textContent).toContain("Request limit reached.");
    fireEvent.click(screen.getByRole("button", { name: "Retry request" }));
    expect(rateLimitRetry).toHaveBeenCalledTimes(1);

    rerender(
      <SectionError message="The service is restarting." status={503} onRetry={serviceRetry} />,
    );
    expect(screen.getByRole("alert").textContent).toContain("Service temporarily unavailable.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(serviceRetry).toHaveBeenCalledTimes(1);
  });

  it("offers a GitHub report path for server failures while preserving retry", () => {
    const onRetry = vi.fn();
    render(<SectionError message="The request failed. Reference: 0123456789abcdef0123456789abcdef01234567." status={500} onRetry={onRetry} />);

    expect(screen.getByRole("alert").textContent).toContain("Unable to load this section.");
    expect(screen.getByRole("link", { name: "Open GitHub issue tracker" }).getAttribute("href")).toBe("/issues");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("does not suggest issue reporting for ordinary permission or rate-limit failures", () => {
    const { rerender } = render(<SectionError message="No access." status={403} onRetry={vi.fn()} />);
    expect(screen.queryByRole("link", { name: "Open GitHub issue tracker" })).toBeNull();

    rerender(<SectionError message="Slow down." status={429} onRetry={vi.fn()} />);
    expect(screen.queryByRole("link", { name: "Open GitHub issue tracker" })).toBeNull();
  });
});
