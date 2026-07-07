import type { DocumentStatus } from "@/lib/api-types";
import { Badge } from "@/components/ui/badge";

export function DocumentStatusBadge({
  status,
  errorMessage,
}: {
  status: DocumentStatus;
  errorMessage?: string | null;
}) {
  switch (status) {
    case "pending":
      return <Badge tone="gray">Pending</Badge>;
    case "processing":
      return (
        <Badge tone="blue" pulse>
          Processing
        </Badge>
      );
    case "ready":
      return <Badge tone="green">Ready</Badge>;
    case "failed":
      return (
        <span
          title={errorMessage ?? "Ingestion failed"}
          className="inline-flex cursor-help"
        >
          <Badge tone="red">Failed</Badge>
        </span>
      );
  }
}
