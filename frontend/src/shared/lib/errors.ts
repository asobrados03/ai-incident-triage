import { ApiError, NetworkError } from "@/api/client";
import type { ValidationIssue } from "@/api/types";

export type FieldErrors = Record<string, string>;

export interface FriendlyError {
  title: string;
  description?: string;
  fields: FieldErrors;
}

const FIELD_LABELS: Record<string, string> = {
  title: "título",
  description: "descripción",
  steps_to_reproduce: "pasos para reproducir",
  expected_behavior: "comportamiento esperado",
  actual_behavior: "comportamiento actual",
  environment: "entorno",
  components: "componentes",
  category: "categoría",
  severity: "severidad",
  priority: "prioridad",
  confidence: "confianza",
  summary: "resumen",
  affected_components: "componentes afectados",
  missing_information: "información faltante",
  justification: "justificación",
  review_comment: "comentario de revisión",
  review_checklist: "checklist de revisión",
  username: "usuario",
  password: "contraseña",
  role: "rol",
};

function labelFor(field: string) {
  return FIELD_LABELS[field] ?? field.replaceAll("_", " ");
}

function issuesFrom(payload: unknown): ValidationIssue[] {
  if (typeof payload !== "object" || payload === null || !("detail" in payload)) {
    return [];
  }
  const detail = (payload as { detail?: unknown }).detail;
  return Array.isArray(detail) ? (detail as ValidationIssue[]) : [];
}

export function fieldErrorsFrom(error: unknown): FieldErrors {
  if (!(error instanceof ApiError)) return {};
  const fields: FieldErrors = {};
  for (const issue of issuesFrom(error.payload)) {
    const field = issue.loc?.filter((part) => part !== "body").at(-1);
    if (typeof field !== "string" || fields[field]) continue;
    fields[field] = friendlyIssue(issue, field);
  }
  return fields;
}

function friendlyIssue(issue: ValidationIssue, field: string): string {
  const type = issue.type ?? "";
  if (type.includes("missing")) return `El campo ${labelFor(field)} es obligatorio.`;
  if (type.includes("too_long") || type.includes("string_too_long")) {
    return `El campo ${labelFor(field)} supera la longitud permitida.`;
  }
  if (type.includes("too_short") || type.includes("string_too_short")) {
    return `El campo ${labelFor(field)} es demasiado corto.`;
  }
  if (type.includes("enum")) return `El valor de ${labelFor(field)} no es válido.`;
  if (type.includes("greater_than") || type.includes("less_than")) {
    return `El valor de ${labelFor(field)} está fuera del rango permitido.`;
  }
  return issue.msg ? `Revisa ${labelFor(field)}: ${issue.msg}` : `Revisa ${labelFor(field)}.`;
}

export function describeError(error: unknown): FriendlyError {
  const fields = fieldErrorsFrom(error);

  if (error instanceof NetworkError) {
    return {
      title: "No se pudo conectar con el backend",
      description:
        "Comprueba que la API esté arrancada en http://127.0.0.1:8000 y vuelve a intentarlo.",
      fields,
    };
  }

  if (error instanceof ApiError) {
    switch (error.status) {
      case 404:
        return {
          title: "No se encontró el recurso",
          description: "Puede que la incidencia se haya eliminado o que el enlace no sea válido.",
          fields,
        };
      case 409:
        return {
          title: "La operación no se puede completar en el estado actual",
          description: error.message,
          fields,
        };
      case 422:
        return {
          title: "Revisa los campos del formulario",
          description: error.message,
          fields,
        };
      case 502:
        return {
          title: "El analizador no está disponible",
          description:
            "El backend no pudo obtener una propuesta de triaje. Vuelve a intentarlo en unos minutos.",
          fields,
        };
      case 504:
        return {
          title: "El analizador tardó demasiado",
          description:
            "Si usas Ollama, el modelo puede necesitar más tiempo. Reintenta el análisis más tarde.",
          fields,
        };
      default:
        return { title: error.message, fields };
    }
  }

  return {
    title: error instanceof Error ? error.message : "Ha ocurrido un error inesperado",
    fields,
  };
}
