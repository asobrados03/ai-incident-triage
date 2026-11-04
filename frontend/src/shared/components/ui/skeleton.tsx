import { cn } from "@/shared/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded-md bg-muted", className)} />;
}

export function TableSkeleton({
  rows = 5,
  columns = 5,
  label = "Cargando datos",
}: {
  rows?: number;
  columns?: number;
  label?: string;
}) {
  return (
    <div role="status" aria-label={label} className="space-y-2 p-4">
      {Array.from({ length: rows }).map((_, row) => (
        <div
          className="grid gap-3"
          key={row}
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
        >
          {Array.from({ length: columns }).map((__, column) => (
            <Skeleton className="h-5" key={column} />
          ))}
        </div>
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  );
}

export function CardsSkeleton({ cards = 3 }: { cards?: number }) {
  return (
    <div role="status" aria-label="Cargando métricas" className="grid gap-4 md:grid-cols-3">
      {Array.from({ length: cards }).map((_, index) => (
        <Skeleton className="h-24" key={index} />
      ))}
      <span className="sr-only">Cargando métricas…</span>
    </div>
  );
}
