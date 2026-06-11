/**
 * TransportBar — the replay control surface. Asserts the scrubber is a real
 * ARIA slider with a meaningful valuetext, the speed segmented control reflects
 * + changes speed, play/pause toggles, and stage ticks render from the player.
 * The player is a hand-built stub (the real hook is covered in eventPlayer.test).
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { EventPlayerControls } from "./eventPlayer";
import { TransportBar } from "./TransportBar";

function makePlayer(over: Partial<EventPlayerControls> = {}): EventPlayerControls {
  return {
    state: {} as never,
    isActive: false,
    isEnded: false,
    play: vi.fn(),
    pause: vi.fn(),
    seek: vi.fn(),
    seekProgress: vi.fn(),
    step: vi.fn(),
    restart: vi.fn(),
    setSpeed: vi.fn(),
    speed: 4,
    elapsedMs: 2000,
    durationMs: 8000,
    stepCount: 8,
    recordedElapsedMs: 1500,
    recordedNodeLatencies: {},
    progress: 0.25,
    stageTicks: [
      { offsetMs: 1000, node: "router" },
      { offsetMs: 4000, node: "trader" },
    ],
    ...over,
  };
}

describe("TransportBar", () => {
  it("exposes an ARIA slider with progress + human valuetext", () => {
    render(<TransportBar player={makePlayer()} />);
    const slider = screen.getByRole("slider", { name: /replay timeline/i });
    expect(slider).toHaveAttribute("aria-valuenow", "25");
    expect(slider).toHaveAttribute("aria-valuetext", "0:02 of 0:08");
    expect(slider).toHaveAttribute("tabindex", "0");
  });

  it("toggles play/pause via the primary button", async () => {
    const play = vi.fn();
    render(<TransportBar player={makePlayer({ isActive: false, play })} />);
    await userEvent.click(screen.getByRole("button", { name: /play replay/i }));
    expect(play).toHaveBeenCalledOnce();
  });

  it("renders a pause affordance while active", () => {
    render(<TransportBar player={makePlayer({ isActive: true })} />);
    expect(screen.getByRole("button", { name: /pause replay/i })).toBeInTheDocument();
  });

  it("marks the current speed as pressed and changes it on click", async () => {
    const setSpeed = vi.fn();
    render(<TransportBar player={makePlayer({ speed: 4, setSpeed })} />);
    expect(screen.getByRole("button", { name: "4×" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userEvent.click(screen.getByRole("button", { name: "8×" }));
    expect(setSpeed).toHaveBeenCalledWith(8);
  });

  it("steps one event on arrow keys from the slider", async () => {
    const step = vi.fn();
    render(<TransportBar player={makePlayer({ step })} />);
    const slider = screen.getByRole("slider", { name: /replay timeline/i });
    slider.focus();
    await userEvent.keyboard("{ArrowRight}");
    await userEvent.keyboard("{ArrowLeft}");
    expect(step).toHaveBeenCalledWith(1);
    expect(step).toHaveBeenCalledWith(-1);
  });

  it("supports ArrowUp/ArrowDown on the slider (ARIA slider pattern)", async () => {
    const step = vi.fn();
    render(<TransportBar player={makePlayer({ step })} />);
    screen.getByRole("slider", { name: /replay timeline/i }).focus();
    await userEvent.keyboard("{ArrowUp}");
    expect(step).toHaveBeenLastCalledWith(1);
    await userEvent.keyboard("{ArrowDown}");
    expect(step).toHaveBeenLastCalledWith(-1);
  });

  it("does not hijack Space when a button has focus (button activates instead)", async () => {
    const play = vi.fn();
    const pause = vi.fn();
    const setSpeed = vi.fn();
    render(
      <TransportBar player={makePlayer({ isActive: false, play, pause, setSpeed })} />,
    );
    const speedBtn = screen.getByRole("button", { name: "8×" });
    speedBtn.focus();
    await userEvent.keyboard(" ");
    // Space must activate the focused button, not toggle playback.
    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();
    expect(setSpeed).toHaveBeenCalledWith(8);
  });

  it("does not hijack Space when a link has focus (link activates instead)", async () => {
    const play = vi.fn();
    const pause = vi.fn();
    render(
      <>
        <a href="/library">Back to library</a>
        <TransportBar player={makePlayer({ isActive: false, play, pause })} />
      </>,
    );
    screen.getByRole("link", { name: /back to library/i }).focus();
    await userEvent.keyboard(" ");
    expect(play).not.toHaveBeenCalled();
    expect(pause).not.toHaveBeenCalled();
  });

  it("renders a stage tick per node_complete with its label", () => {
    render(<TransportBar player={makePlayer()} />);
    expect(screen.getByTitle("Router")).toBeInTheDocument();
    expect(screen.getByTitle("Trader")).toBeInTheDocument();
  });
});
