import { useState } from "react";
import { X } from "lucide-react";

export function ChipInput({
  id,
  label,
  value,
  onChange,
  max = 20,
  placeholder = "Escribe y pulsa Enter",
  disabled = false,
}: {
  id: string;
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  max?: number;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  function add(raw: string) {
    const items = raw
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    if (items.length === 0) return;
    const next = [...value];
    for (const item of items) {
      if (next.includes(item)) continue;
      if (next.length >= max) {
        setMessage(`Puedes añadir como máximo ${max} componentes.`);
        break;
      }
      next.push(item);
    }
    onChange(next);
    setDraft("");
    if (next.length < max) setMessage(null);
  }

  function remove(item: string) {
    onChange(value.filter((entry) => entry !== item));
    setMessage(null);
  }

  return (
    <div className="space-y-1">
      <label className="block space-y-1">
        <span className="text-sm font-medium">{label}</span>
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-border bg-background p-2 focus-within:ring-2 focus-within:ring-primary">
          {value.map((item) => (
            <span
              className="inline-flex items-center gap-1 rounded-full bg-muted px-2.5 py-1 text-xs"
              key={item}
            >
              {item}
              <button
                type="button"
                className="rounded-full p-0.5 hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                aria-label={`Quitar ${item}`}
                onClick={() => remove(item)}
                disabled={disabled}
              >
                <X className="h-3 w-3" aria-hidden="true" />
              </button>
            </span>
          ))}
          <input
            id={id}
            className="min-w-40 flex-1 bg-transparent px-1 py-1 text-sm outline-none"
            value={draft}
            placeholder={value.length === 0 ? placeholder : ""}
            disabled={disabled || value.length >= max}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === ",") {
                event.preventDefault();
                add(draft);
              }
              if (event.key === "Backspace" && draft === "" && value.length > 0) {
                remove(value[value.length - 1]);
              }
            }}
            onBlur={() => add(draft)}
          />
        </div>
      </label>
      <p className="text-xs text-muted-foreground">
        {value.length}/{max} componentes
      </p>
      {message && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {message}
        </p>
      )}
    </div>
  );
}
