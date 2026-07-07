import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { Source } from "@/lib/api-types";
import { ChatMessage } from "@/components/chat/chat-message";

const SOURCES: Source[] = [
  {
    index: 1,
    chunk_id: "chunk-1",
    document_id: "doc-1",
    document_title: "Feline Biology",
    page_number: 12,
    snippet: "Domestic cats purr at a frequency of roughly 25 Hz.",
    score: 0.0451,
  },
  {
    index: 2,
    chunk_id: "chunk-2",
    document_id: "doc-2",
    document_title: "Animal Acoustics",
    page_number: null,
    snippet: "Purring is produced during both inhalation and exhalation.",
    score: 0.0312,
  },
];

describe("ChatMessage citation parsing", () => {
  it("turns [n] markers into clickable citation chips", () => {
    render(
      <ChatMessage
        role="assistant"
        content="Cats purr at about 25 Hz [1] during both breath phases [2]."
        sources={SOURCES}
      />,
    );

    expect(
      screen.getByRole("button", { name: /citation 1: feline biology/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /citation 2: animal acoustics/i }),
    ).toBeInTheDocument();
    // The literal bracket markers are replaced by chips.
    expect(screen.queryByText("[1]", { exact: false })).not.toBeInTheDocument();
  });

  it("reveals the source popover when a chip is clicked", async () => {
    const user = userEvent.setup();
    render(
      <ChatMessage
        role="assistant"
        content="Cats purr at about 25 Hz [1]."
        sources={SOURCES}
      />,
    );

    const snippet = SOURCES[0].snippet;
    expect(screen.queryByText(snippet)).not.toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /citation 1: feline biology/i }),
    );

    const snippetEl = screen.getByText(snippet);
    expect(snippetEl).toBeInTheDocument();

    // Scope to the popover card ("Page 12" also appears in the sources row).
    const popover = snippetEl.closest("div");
    expect(popover).not.toBeNull();
    const inPopover = within(popover as HTMLElement);
    expect(inPopover.getByText(/page 12/i)).toBeInTheDocument();
    expect(inPopover.getByText(/score 0\.045/i)).toBeInTheDocument();
    expect(
      inPopover.getByRole("link", { name: /open document/i }),
    ).toHaveAttribute("href", "/documents/doc-1");
  });

  it("leaves markers without a matching source as plain text", () => {
    render(
      <ChatMessage
        role="assistant"
        content="An unmatched marker [7] stays as text."
        sources={SOURCES}
      />,
    );

    expect(screen.getByText(/\[7\]/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /citation 7/i }),
    ).not.toBeInTheDocument();
  });

  it("renders a numbered Sources row under assistant messages", () => {
    render(
      <ChatMessage
        role="assistant"
        content="Answer [1] and [2]."
        sources={SOURCES}
      />,
    );

    expect(screen.getByText(/^sources$/i)).toBeInTheDocument();
    const rowLinks = screen
      .getAllByRole("link")
      .filter((a) => a.getAttribute("href")?.startsWith("/documents/"));
    expect(rowLinks).toHaveLength(2);
  });

  it("renders user messages as plain right-aligned bubbles without chips", () => {
    render(
      <ChatMessage role="user" content="What about [1] brackets?" sources={null} />,
    );
    expect(screen.getByText(/what about \[1\] brackets\?/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
