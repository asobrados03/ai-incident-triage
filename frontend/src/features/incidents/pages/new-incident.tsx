import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router-dom";
import { z } from "zod";

import { apiClient } from "@/api/client";
import { ChipInput } from "@/shared/components/ui/chip-input";
import { ErrorAlert } from "@/shared/components/ui/error-alert";
import { Spinner } from "@/shared/components/ui/spinner";
import { fieldErrorsFrom } from "@/shared/lib/errors";

const schema = z.object({
  title: z.string().min(1, "El título es obligatorio").max(200, "Máximo 200 caracteres"),
  description: z
    .string()
    .min(1, "La descripción es obligatoria")
    .max(5000, "Máximo 5000 caracteres"),
  steps_to_reproduce: z.string().max(5000, "Máximo 5000 caracteres").optional(),
  expected_behavior: z.string().max(2000, "Máximo 2000 caracteres").optional(),
  actual_behavior: z.string().max(2000, "Máximo 2000 caracteres").optional(),
  environment: z.string().max(1000, "Máximo 1000 caracteres").optional(),
});
type FormValues = z.infer<typeof schema>;

const TEXT_FIELDS = [
  { name: "title", label: "Título", multiline: false, max: 200, required: true },
  { name: "description", label: "Descripción", multiline: true, max: 5000, required: true },
  {
    name: "steps_to_reproduce",
    label: "Pasos para reproducir",
    multiline: true,
    max: 5000,
    required: false,
  },
  {
    name: "expected_behavior",
    label: "Comportamiento esperado",
    multiline: true,
    max: 2000,
    required: false,
  },
  {
    name: "actual_behavior",
    label: "Comportamiento actual",
    multiline: true,
    max: 2000,
    required: false,
  },
  { name: "environment", label: "Entorno", multiline: false, max: 1000, required: false },
] as const;

export function NewIncidentPage() {
  const navigate = useNavigate();
  const [components, setComponents] = useState<string[]>([]);
  const form = useForm<FormValues>({ resolver: zodResolver(schema) });
  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      apiClient.createIncident({
        ...values,
        ...(components.length > 0 ? { components } : {}),
      }),
    onSuccess: (incident) => navigate(`/incidents/${incident.id}`),
  });
  const serverFields = fieldErrorsFrom(mutation.error);

  return (
    <section className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Nueva incidencia</h1>
        <p className="text-muted-foreground">
          Describe el problema con el detalle disponible; la IA propondrá el triaje.
        </p>
      </div>
      <form
        className="space-y-4 rounded-lg border border-border p-6"
        onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
        noValidate
      >
        {TEXT_FIELDS.map((field) => {
          const error = form.formState.errors[field.name]?.message ?? serverFields[field.name];
          return (
            <label className="block space-y-1" key={field.name}>
              <span className="text-sm font-medium">
                {field.label}
                {field.required ? " *" : ""}
              </span>
              {field.multiline ? (
                <textarea
                  aria-label={field.name}
                  className="min-h-24 w-full rounded-md border border-border bg-background p-3"
                  maxLength={field.max}
                  {...form.register(field.name)}
                />
              ) : (
                <input
                  aria-label={field.name}
                  className="h-10 w-full rounded-md border border-border bg-background px-3"
                  maxLength={field.max}
                  {...form.register(field.name)}
                />
              )}
              {error && (
                <span role="alert" className="text-sm text-red-600 dark:text-red-400">
                  {String(error)}
                </span>
              )}
            </label>
          );
        })}

        <ChipInput
          id="components"
          label="Componentes afectados"
          value={components}
          onChange={setComponents}
          max={20}
          placeholder="frontend, api, base de datos…"
          disabled={mutation.isPending}
        />

        {mutation.isError && <ErrorAlert error={mutation.error} />}

        <div className="flex flex-wrap gap-3">
          <button
            className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground disabled:opacity-60"
            type="submit"
            disabled={mutation.isPending}
          >
            {mutation.isPending && <Spinner label="Creando incidencia" />}
            {mutation.isPending ? "Creando…" : "Crear incidencia"}
          </button>
          <p className="self-center text-xs text-muted-foreground">
            Los campos opcionales pueden completarse después.
          </p>
        </div>
      </form>
    </section>
  );
}
