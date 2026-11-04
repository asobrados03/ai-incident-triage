import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { apiClient } from "@/api/client";
import type { IncidentResponse, TriageReviewPayload, TriageResult } from "@/api/types";
import { ErrorAlert } from "@/shared/components/ui/error-alert";
import { Spinner } from "@/shared/components/ui/spinner";

const CATEGORIES = ["bug", "feature", "documentation", "configuration", "performance"] as const;
const SEVERITIES = ["low", "medium", "high", "critical"] as const;
const PRIORITIES = ["low", "medium", "high", "urgent"] as const;
const CONFIDENCES = ["low", "medium", "high"] as const;

const MAX_COMMENT = 2000;
const COMMENT_WARNING = 1800;

export const REVIEW_CHECKLIST = [
  "Revisé la categoría y el resumen",
  "Revisé la severidad y la prioridad",
  "Revisé los componentes afectados",
  "Revisé la información faltante",
] as const;

const schema = z.object({
  category: z.enum(CATEGORIES),
  severity: z.enum(SEVERITIES),
  priority: z.enum(PRIORITIES),
  confidence: z.enum(CONFIDENCES),
  summary: z.string().min(1, "El resumen es obligatorio").max(1000),
  affected_components: z.string().max(2000).optional(),
  justification: z.string().min(1, "La justificación es obligatoria").max(2000),
  review_comment: z.string().max(MAX_COMMENT).optional(),
});
type Values = z.infer<typeof schema>;

const COMPARED_FIELDS = [
  { name: "category", label: "Categoría" },
  { name: "severity", label: "Severidad" },
  { name: "priority", label: "Prioridad" },
  { name: "confidence", label: "Confianza" },
  { name: "summary", label: "Resumen" },
  { name: "affected_components", label: "Componentes afectados" },
  { name: "justification", label: "Justificación" },
] as const;

type ComparedField = (typeof COMPARED_FIELDS)[number]["name"];

function proposalValue(proposal: TriageResult, field: ComparedField): string {
  return field === "affected_components"
    ? proposal.affected_components.join(", ")
    : String(proposal[field]);
}

function sameValue(left: string, right: string) {
  return left.trim() === right.trim();
}

export function ReviewForm({
  incident,
  onSuccess,
}: {
  incident: IncidentResponse;
  onSuccess: (incident: IncidentResponse) => void;
}) {
  const proposal = incident.triage!;
  const [checkedItems, setCheckedItems] = useState<string[]>([]);
  const [selectedMissing, setSelectedMissing] = useState<string[]>([]);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      category: proposal.category,
      severity: proposal.severity,
      priority: proposal.priority,
      confidence: proposal.confidence,
      summary: proposal.summary,
      affected_components: proposal.affected_components.join(", "),
      justification: proposal.justification,
      review_comment: "",
    },
  });
  const mutation = useMutation({
    mutationFn: (payload: TriageReviewPayload) => apiClient.reviewIncident(incident.id, payload),
    onSuccess,
  });

  const values = form.watch();
  const changes = COMPARED_FIELDS.filter(
    (field) => !sameValue(values[field.name] ?? "", proposalValue(proposal, field.name)),
  );
  const rawComment = values.review_comment?.trim() ?? "";
  const structuredMissing =
    selectedMissing.length > 0
      ? `Información faltante necesaria:\n${selectedMissing.map((item) => `- ${item}`).join("\n")}`
      : "";
  const combinedComment = [rawComment, structuredMissing].filter(Boolean).join("\n\n");
  const overLimit = combinedComment.length > MAX_COMMENT;
  const nearLimit = combinedComment.length >= COMMENT_WARNING;
  const blocked = overLimit || mutation.isPending;

  function toggleChecklist(item: string) {
    setCheckedItems((current) =>
      current.includes(item) ? current.filter((value) => value !== item) : [...current, item],
    );
  }

  function toggleMissing(item: string) {
    setSelectedMissing((current) =>
      current.includes(item) ? current.filter((value) => value !== item) : [...current, item],
    );
  }

  function submit(values: Values) {
    if (overLimit) return;
    mutation.mutate({
      category: values.category,
      severity: values.severity,
      priority: values.priority,
      confidence: values.confidence,
      summary: values.summary.trim(),
      justification: values.justification.trim(),
      affected_components: splitList(values.affected_components),
      missing_information: selectedMissing,
      review_comment: combinedComment || undefined,
      review_checklist: checkedItems.length > 0 ? checkedItems : undefined,
    });
  }

  function acceptProposal() {
    if (overLimit) return;
    mutation.mutate({
      missing_information: selectedMissing,
      review_comment: combinedComment || "Aceptada sin cambios",
      review_checklist: checkedItems.length > 0 ? checkedItems : undefined,
    });
  }

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      if (!(event.ctrlKey || event.metaKey) || event.key !== "Enter") return;
      event.preventDefault();
      if (blocked) return;
      if (event.shiftKey) {
        acceptProposal();
      } else {
        void form.handleSubmit(submit)();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  });

  return (
    <form
      id="review-form"
      className="space-y-4 rounded-lg border border-border p-5"
      onSubmit={form.handleSubmit(submit)}
      aria-label="Formulario de revisión humana"
    >
      <div>
        <h2 className="text-xl font-semibold">Revisión humana</h2>
        <p className="text-sm text-muted-foreground">
          Corrige solo lo necesario. Cada campo muestra el valor de la IA; los cambios se marcan
          antes de enviar.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <SelectField
          label="Categoría"
          name="category"
          options={CATEGORIES}
          register={form.register}
          proposal={proposalValue(proposal, "category")}
          current={values.category}
          onAccept={() => form.setValue("category", proposal.category, { shouldDirty: true })}
        />
        <SelectField
          label="Severidad"
          name="severity"
          options={SEVERITIES}
          register={form.register}
          proposal={proposalValue(proposal, "severity")}
          current={values.severity}
          onAccept={() => form.setValue("severity", proposal.severity, { shouldDirty: true })}
        />
        <SelectField
          label="Prioridad"
          name="priority"
          options={PRIORITIES}
          register={form.register}
          proposal={proposalValue(proposal, "priority")}
          current={values.priority}
          onAccept={() => form.setValue("priority", proposal.priority, { shouldDirty: true })}
        />
        <SelectField
          label="Confianza"
          name="confidence"
          options={CONFIDENCES}
          register={form.register}
          proposal={proposalValue(proposal, "confidence")}
          current={values.confidence}
          onAccept={() => form.setValue("confidence", proposal.confidence, { shouldDirty: true })}
        />
      </div>

      <div className="block space-y-1">
        <label className="text-sm font-medium" htmlFor="review-summary">
          Resumen final
        </label>
        <FieldHint
          proposal={proposalValue(proposal, "summary")}
          current={values.summary}
          onAccept={() => form.setValue("summary", proposal.summary, { shouldDirty: true })}
        />
        <textarea
          id="review-summary"
          className="min-h-20 w-full rounded-md border border-border bg-background p-3"
          {...form.register("summary")}
        />
        {form.formState.errors.summary && (
          <span role="alert" className="text-sm text-red-600 dark:text-red-400">
            {form.formState.errors.summary.message}
          </span>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="block space-y-1">
          <label className="text-sm font-medium" htmlFor="review-components">
            Componentes afectados (separados por coma)
          </label>
          <FieldHint
            proposal={proposalValue(proposal, "affected_components") || "—"}
            current={values.affected_components ?? ""}
            onAccept={() =>
              form.setValue("affected_components", proposal.affected_components.join(", "), {
                shouldDirty: true,
              })
            }
          />
          <input
            id="review-components"
            className="h-10 w-full rounded-md border border-border bg-background px-3"
            {...form.register("affected_components")}
          />
        </div>
        <div className="block space-y-1">
          <span className="text-sm font-medium">Información faltante necesaria</span>
          <p className="text-xs text-muted-foreground">
            Marca solo los faltantes que realmente bloquean el triaje. Se añadirán al comentario.
          </p>
          {proposal.missing_information.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              La propuesta no detectó información faltante.
            </p>
          ) : (
            <fieldset className="space-y-2 rounded-md border border-border p-3">
              <legend className="px-1 text-sm">
                Faltantes propuestos ({selectedMissing.length}/{proposal.missing_information.length}
                )
              </legend>
              {proposal.missing_information.map((item) => (
                <label className="flex items-start gap-2 text-sm" key={item}>
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={selectedMissing.includes(item)}
                    onChange={() => toggleMissing(item)}
                  />
                  <span>{item}</span>
                </label>
              ))}
            </fieldset>
          )}
        </div>
      </div>

      <div className="block space-y-1">
        <label className="text-sm font-medium" htmlFor="review-justification">
          Justificación final
        </label>
        <FieldHint
          proposal={proposalValue(proposal, "justification")}
          current={values.justification}
          onAccept={() =>
            form.setValue("justification", proposal.justification, { shouldDirty: true })
          }
        />
        <textarea
          id="review-justification"
          className="min-h-20 w-full rounded-md border border-border bg-background p-3"
          {...form.register("justification")}
        />
        {form.formState.errors.justification && (
          <span role="alert" className="text-sm text-red-600 dark:text-red-400">
            {form.formState.errors.justification.message}
          </span>
        )}
      </div>

      <fieldset className="space-y-2 rounded-md border border-border p-4">
        <legend className="px-1 text-sm font-medium">
          Checklist de revisión ({checkedItems.length}/{REVIEW_CHECKLIST.length})
        </legend>
        <div className="grid gap-2 md:grid-cols-2">
          {REVIEW_CHECKLIST.map((item) => (
            <label className="flex items-start gap-2 text-sm" key={item}>
              <input
                type="checkbox"
                className="mt-1"
                checked={checkedItems.includes(item)}
                onChange={() => toggleChecklist(item)}
              />
              <span>{item}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <div className="block space-y-1">
        <label className="text-sm font-medium" htmlFor="review-comment">
          Comentario de revisión
        </label>
        <textarea
          id="review-comment"
          className="min-h-24 w-full rounded-md border border-border bg-background p-3"
          placeholder="Indica qué verificaste o por qué cambiaste un campo…"
          {...form.register("review_comment")}
        />
        <span
          className={`text-xs ${
            overLimit
              ? "font-medium text-red-600 dark:text-red-400"
              : nearLimit
                ? "text-amber-700 dark:text-amber-400"
                : "text-muted-foreground"
          }`}
          aria-live="polite"
        >
          {combinedComment.length}/{MAX_COMMENT} caracteres
          {selectedMissing.length > 0 && " (incluye la información faltante marcada)"}
          {overLimit && " · supera el límite: reduce el comentario o desmarca faltantes"}
        </span>
      </div>

      <section
        aria-label="Resumen previo al envío"
        className="rounded-md border border-border bg-muted/40 p-4 text-sm"
      >
        <h3 className="font-semibold">Resumen previo al envío</h3>
        {changes.length === 0 ? (
          <p className="mt-1 text-muted-foreground">
            Sin cambios respecto a la propuesta de la IA.
          </p>
        ) : (
          <ul className="mt-2 space-y-1" aria-live="polite">
            {changes.map((field) => (
              <li key={field.name}>
                <span className="font-medium">{field.label}: </span>
                <span className="text-muted-foreground">
                  {proposalValue(proposal, field.name) || "—"}
                </span>{" "}
                → <span>{values[field.name]?.trim() || "—"}</span>
              </li>
            ))}
          </ul>
        )}
        {combinedComment && (
          <p className="mt-2 whitespace-pre-wrap">
            <span className="font-medium">Comentario: </span>
            {combinedComment}
          </p>
        )}
        <p className="mt-2 text-xs text-muted-foreground">
          Atajos: <kbd className="rounded border px-1">Ctrl</kbd>+
          <kbd className="rounded border px-1">Enter</kbd> guardar corrección ·{" "}
          <kbd className="rounded border px-1">Ctrl</kbd>+
          <kbd className="rounded border px-1">Shift</kbd>+
          <kbd className="rounded border px-1">Enter</kbd> aceptar propuesta.
        </p>
      </section>

      {overLimit && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          El comentario final supera los {MAX_COMMENT} caracteres. Acorta el texto o desmarca
          faltantes antes de guardar.
        </p>
      )}
      {mutation.isError && <ErrorAlert error={mutation.error} />}
      <div aria-live="polite" className="sr-only">
        {mutation.isSuccess ? "Revisión guardada." : ""}
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
          type="submit"
          disabled={blocked}
        >
          {mutation.isPending && <Spinner label="Guardando revisión" />}
          {mutation.isPending ? "Guardando…" : "Guardar revisión"}
        </button>
        <button
          className="inline-flex h-10 items-center gap-2 rounded-md border border-border px-4 text-sm font-medium disabled:opacity-60"
          type="button"
          disabled={blocked}
          onClick={acceptProposal}
        >
          Aceptar propuesta
        </button>
      </div>
    </form>
  );
}

function FieldHint({
  proposal,
  current,
  onAccept,
}: {
  proposal: string;
  current: string;
  onAccept: () => void;
}) {
  const changed = !sameValue(current, proposal);
  return (
    <span className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <span>
        IA: <span className="text-foreground">{proposal || "—"}</span>
      </span>
      {changed ? (
        <>
          <span className="rounded-full bg-amber-200 px-2 py-0.5 font-medium text-amber-900 dark:bg-amber-800 dark:text-amber-50">
            modificado
          </span>
          <button
            type="button"
            className="rounded border border-border px-2 py-0.5 text-xs hover:bg-muted"
            onClick={onAccept}
          >
            Aceptar valor IA
          </button>
        </>
      ) : (
        <span className="rounded-full bg-muted px-2 py-0.5">igual</span>
      )}
    </span>
  );
}

function SelectField({
  label,
  name,
  options,
  register,
  proposal,
  current,
  onAccept,
}: {
  label: string;
  name: "category" | "severity" | "priority" | "confidence";
  options: readonly string[];
  register: ReturnType<typeof useForm<Values>>["register"];
  proposal: string;
  current: string;
  onAccept: () => void;
}) {
  return (
    <div className="block space-y-1">
      <label className="block space-y-1">
        <span className="text-sm font-medium">{label}</span>
        <select
          className="h-10 w-full rounded-md border border-border bg-background px-3"
          {...register(name)}
        >
          {options.map((option) => (
            <option key={option}>{option}</option>
          ))}
        </select>
      </label>
      <FieldHint proposal={proposal} current={current} onAccept={onAccept} />
    </div>
  );
}

function splitList(raw: string | undefined) {
  if (!raw) return [];
  return Array.from(
    new Set(
      raw
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}
