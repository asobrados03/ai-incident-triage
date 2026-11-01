import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { apiClient } from "@/api/client";
import type { IncidentResponse } from "@/api/types";
import type { UseFormRegister } from "react-hook-form";

const schema = z.object({
  category: z.enum(["bug", "feature", "documentation", "configuration", "performance"]).optional(),
  severity: z.enum(["low", "medium", "high", "critical"]).optional(),
  priority: z.enum(["low", "medium", "high", "urgent"]).optional(),
  summary: z.string().optional(),
  review_comment: z.string().max(2000).optional(),
});
type Values = z.infer<typeof schema>;

export function ReviewForm({ incident, onSuccess }: { incident: IncidentResponse; onSuccess: (incident: IncidentResponse) => void }) {
  const form = useForm<Values>({ resolver: zodResolver(schema) });
  const mutation = useMutation({
    mutationFn: (values: Values) => apiClient.reviewIncident(incident.id, values),
    onSuccess,
  });
  const proposal = incident.triage!;

  return (
    <form className="space-y-4 rounded-lg border border-border p-5" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
      <div>
        <h2 className="text-xl font-semibold">Revisión humana</h2>
        <p className="text-sm text-muted-foreground">Compara la propuesta con el resultado final y corrige solo lo necesario.</p>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <SelectField label="Categoría" name="category" options={["bug", "feature", "documentation", "configuration", "performance"]} defaultValue={proposal.category} register={form.register} />
        <SelectField label="Severidad" name="severity" options={["low", "medium", "high", "critical"]} defaultValue={proposal.severity} register={form.register} />
        <SelectField label="Prioridad" name="priority" options={["low", "medium", "high", "urgent"]} defaultValue={proposal.priority} register={form.register} />
      </div>
      <label className="block space-y-1"><span className="text-sm font-medium">Resumen final</span><textarea className="min-h-20 w-full rounded-md border bg-background p-3" defaultValue={proposal.summary} {...form.register("summary")} /></label>
      <label className="block space-y-1"><span className="text-sm font-medium">Checklist / comentario de revisión</span><textarea className="min-h-24 w-full rounded-md border bg-background p-3" placeholder="Indica qué verificaste…" {...form.register("review_comment")} /></label>
      {mutation.isError && <p role="alert" className="text-sm text-red-600">{mutation.error.message}</p>}
      <button className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground" disabled={mutation.isPending}>{mutation.isPending ? "Guardando…" : "Guardar revisión"}</button>
    </form>
  );
}

function SelectField({ label, name, options, defaultValue, register }: { label: string; name: "category" | "severity" | "priority"; options: string[]; defaultValue: string; register: UseFormRegister<Values> }) {
  return <label className="block space-y-1"><span className="text-sm font-medium">{label}</span><select className="h-10 w-full rounded-md border bg-background px-3" defaultValue={defaultValue} {...register(name)}>{options.map((option) => <option key={option}>{option}</option>)}</select></label>;
}
