import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  MAX_FILE_SIZE_BYTES,
  UploadDropzone,
  validateFile,
} from "@/components/documents/upload-dropzone";

function makeFile(name: string, type: string, size?: number): File {
  const file = new File(["content"], name, { type });
  if (size !== undefined) {
    Object.defineProperty(file, "size", { value: size });
  }
  return file;
}

function changeInput(files: File[]) {
  const input = screen.getByTestId("file-input");
  fireEvent.change(input, { target: { files } });
}

describe("UploadDropzone validation", () => {
  it("rejects an .exe file with a friendly error", () => {
    const onFileAccepted = vi.fn();
    render(<UploadDropzone onFileAccepted={onFileAccepted} />);

    changeInput([makeFile("malware.exe", "application/x-msdownload")]);

    expect(onFileAccepted).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      /not a supported file type/i,
    );
  });

  it("rejects a file larger than 20 MB", () => {
    const onFileAccepted = vi.fn();
    render(<UploadDropzone onFileAccepted={onFileAccepted} />);

    changeInput([
      makeFile("big.pdf", "application/pdf", MAX_FILE_SIZE_BYTES + 1),
    ]);

    expect(onFileAccepted).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent(/limit is 20 MB/i);
  });

  it("accepts a valid pdf and passes it to onFileAccepted", () => {
    const onFileAccepted = vi.fn();
    render(<UploadDropzone onFileAccepted={onFileAccepted} />);

    const pdf = makeFile("notes.pdf", "application/pdf");
    changeInput([pdf]);

    expect(onFileAccepted).toHaveBeenCalledTimes(1);
    expect(onFileAccepted).toHaveBeenCalledWith(pdf);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("accepts txt and md files by extension even without a mime type", () => {
    expect(validateFile(makeFile("readme.md", ""))).toBeNull();
    expect(validateFile(makeFile("notes.txt", ""))).toBeNull();
    expect(validateFile(makeFile("archive.zip", ""))).toMatch(
      /not a supported file type/i,
    );
  });

  it("accepts exactly 20 MB but rejects one byte over", () => {
    expect(
      validateFile(makeFile("edge.pdf", "application/pdf", MAX_FILE_SIZE_BYTES)),
    ).toBeNull();
    expect(
      validateFile(
        makeFile("over.pdf", "application/pdf", MAX_FILE_SIZE_BYTES + 1),
      ),
    ).toMatch(/limit is 20 MB/i);
  });
});
