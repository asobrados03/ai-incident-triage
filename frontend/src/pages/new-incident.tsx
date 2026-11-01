import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { apiClient } from "@/api/client";

const schema = z.object({
  title: z.string().min(1).max(200),
  description: z.string().min(1).max(5000),
  steps_to_reproduce: z.string().max(5000).optional(),
  expected_behavior: z.string().max(2000).optional(),
  actual_behavior: z.string().max(2000).optional(),
  environment: z.string().max(1000).optional(),
  components: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

export function NewIncidentPage() {
  const navigate = useNavigate();
  const form = useForm<FormValues>({ resolver: zodResolver(schema) });
  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      apiClient.createIncident({
        ...values,
        components: values.components
          ?.split(",")
          .map((component) => component.trim())
          .filter(Boolean),
      }),
    onSuccess: (incident) => navigate(`/incidents/${incident.id}`),
  });

  return (
    <section className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Nueva incidencia</h1>
        <p className="text-muted-foreground">Describe el problema para iniciar el triaje.</p>
      </div>
      <form className="space-y-4 rounded-lg border border-border p-6" onSubmit={form.handleSubmit((values) => mutation.mutate(values))}>
        {(["title", "description", "steps_to_reproduce", "expected_behavior", "actual_behavior", "environment", "components"] as const).map((field) => (
          <label className="block space-y-1" key={field}>
            <span className="text-sm font-medium">{field === "components" ? "Componentes (separados por coma)" : field.replaceAll("_", " ")}</span>
            {field === "description" || field === "steps_to_reproduce" || field === "expected_behavior" || field === "actual_behavior" ? (
              <textarea className="min-h-24 w-full rounded-md border bg-background p-3" {...form.register(field)} />
            ) : (
              <input className="h-10 w-full rounded-md border bg-background px-3" {...form.register(field)} />
            )}
          </label>
        ))}
        {mutation.isError && <p role="alert" className="text-sm text-red-600">{mutation.error.message}</p>}
        <button className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground" disabled={mutation.isPending}>
          {mutation.isPending ? "Creando…" : "Crear incidencia"}
        </button>
      </form>
    </section>
  );
}
