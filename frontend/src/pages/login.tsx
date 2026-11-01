import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { ApiError } from "@/api/client";
import { useAuth } from "@/auth";

const schema = z.object({
  username: z.string().min(1, "Indica el usuario"),
  password: z.string().min(1, "Indica la contraseña"),
});
type FormValues = z.infer<typeof schema>;

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<FormValues>({ resolver: zodResolver(schema) });

  async function onSubmit(values: FormValues) {
    setError(null);
    try {
      await login(values.username, values.password);
      const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
      navigate(from ?? "/", { replace: true });
    } catch (submitError) {
      setError(submitError instanceof ApiError ? submitError.message : "No se pudo iniciar sesión");
    }
  }

  return (
    <section className="mx-auto max-w-md space-y-6">
      <div>
        <p className="text-sm font-medium text-primary">Acceso seguro</p>
        <h1 className="text-3xl font-semibold">Iniciar sesión</h1>
      </div>
      <form className="space-y-4 rounded-lg border border-border p-6" onSubmit={form.handleSubmit(onSubmit)}>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Usuario</span>
          <input className="h-10 w-full rounded-md border bg-background px-3" {...form.register("username")} />
          {form.formState.errors.username && <span className="text-sm text-red-600">{form.formState.errors.username.message}</span>}
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Contraseña</span>
          <input className="h-10 w-full rounded-md border bg-background px-3" type="password" {...form.register("password")} />
          {form.formState.errors.password && <span className="text-sm text-red-600">{form.formState.errors.password.message}</span>}
        </label>
        {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
        <button className="h-10 w-full rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </section>
  );
}
