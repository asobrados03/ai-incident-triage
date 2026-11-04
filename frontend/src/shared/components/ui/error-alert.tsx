import type { FieldErrors } from "@/shared/lib/errors";
import { describeError } from "@/shared/lib/errors";

export function ErrorAlert({ error, className }: { error: unknown; className?: string }) {
  const friendly = describeError(error);
  return (
    <div
      role="alert"
      className={
        className ??
        "rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-100"
      }
      aria-live="assertive"
    >
      <p className="font-medium">{friendly.title}</p>
      {friendly.description && friendly.description !== friendly.title && (
        <p className="mt-1">{friendly.description}</p>
      )}
    </div>
  );
}

export function FieldError({ errors, field }: { errors: FieldErrors; field: string }) {
  const message = errors[field];
  if (!message) return null;
  return (
    <span role="alert" className="text-sm text-red-600 dark:text-red-400">
      {message}
    </span>
  );
}
