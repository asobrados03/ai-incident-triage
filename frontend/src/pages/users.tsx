import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { apiClient } from "@/api/client";
import type { Role, UserResponse } from "@/api/types";

const ROLES = ["reader", "writer", "admin"] as const;

const schema = z.object({
  username: z
    .string()
    .min(3, "Mínimo 3 caracteres")
    .max(100)
    .regex(/^[A-Za-z0-9._-]+$/, "Solo letras, números, punto, guion y guion bajo"),
  password: z.string().min(12, "Mínimo 12 caracteres").max(200),
  role: z.enum(ROLES),
});
type Values = z.infer<typeof schema>;

export function UsersPage() {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["users"],
    queryFn: ({ signal }) => apiClient.listUsers({ limit: 100 }, signal),
  });
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { username: "", password: "", role: "reader" },
  });

  function refresh() {
    void queryClient.invalidateQueries({ queryKey: ["users"] });
  }

  const create = useMutation({
    mutationFn: (values: Values) => apiClient.createUser(values),
    onSuccess: () => {
      form.reset({ username: "", password: "", role: "reader" });
      refresh();
    },
  });
  const update = useMutation({
    mutationFn: ({
      user,
      payload,
    }: {
      user: UserResponse;
      payload: { role?: Role; active?: boolean };
    }) => apiClient.updateUser(user.id, payload),
    onSuccess: refresh,
  });

  return (
    <section className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Usuarios</h1>
        <p className="text-muted-foreground">
          Gestión de acceso: roles jerárquicos y desactivación sin borrar el histórico.
        </p>
      </div>

      <form
        className="space-y-4 rounded-lg border border-border p-5"
        onSubmit={form.handleSubmit((values) => create.mutate(values))}
      >
        <h2 className="text-xl font-semibold">Crear usuario</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <label className="block space-y-1">
            <span className="text-sm font-medium">Usuario</span>
            <input
              className="h-10 w-full rounded-md border bg-background px-3"
              autoComplete="off"
              {...form.register("username")}
            />
            {form.formState.errors.username && (
              <span className="text-sm text-red-600">{form.formState.errors.username.message}</span>
            )}
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Contraseña inicial</span>
            <input
              className="h-10 w-full rounded-md border bg-background px-3"
              type="password"
              autoComplete="new-password"
              {...form.register("password")}
            />
            {form.formState.errors.password && (
              <span className="text-sm text-red-600">{form.formState.errors.password.message}</span>
            )}
          </label>
          <label className="block space-y-1">
            <span className="text-sm font-medium">Rol</span>
            <select
              className="h-10 w-full rounded-md border bg-background px-3"
              {...form.register("role")}
            >
              {ROLES.map((role) => (
                <option key={role}>{role}</option>
              ))}
            </select>
          </label>
        </div>
        {create.isError && (
          <p role="alert" className="text-sm text-red-600">
            {create.error.message}
          </p>
        )}
        <button
          className="h-10 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground"
          disabled={create.isPending}
        >
          {create.isPending ? "Creando…" : "Crear usuario"}
        </button>
      </form>

      {query.isPending && <p role="status">Cargando usuarios…</p>}
      {query.isError && <p role="alert">{query.error.message}</p>}
      {update.isError && (
        <p role="alert" className="text-sm text-red-600">
          {update.error.message}
        </p>
      )}

      {query.isSuccess && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-muted/60">
              <tr>
                <th className="px-4 py-3 font-medium">Usuario</th>
                <th className="px-4 py-3 font-medium">Rol</th>
                <th className="px-4 py-3 font-medium">Estado</th>
                <th className="px-4 py-3 font-medium">Último acceso</th>
                <th className="px-4 py-3 font-medium">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {query.data.items.map((user) => (
                <tr key={user.id} className={user.active ? undefined : "opacity-60"}>
                  <td className="px-4 py-3 font-medium">{user.username}</td>
                  <td className="px-4 py-3">
                    <select
                      className="h-9 rounded-md border bg-background px-2"
                      aria-label={`Rol de ${user.username}`}
                      value={user.role}
                      disabled={update.isPending}
                      onChange={(event) =>
                        update.mutate({
                          user,
                          payload: { role: event.target.value as Role },
                        })
                      }
                    >
                      {ROLES.map((role) => (
                        <option key={role}>{role}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        user.active
                          ? "bg-emerald-100 text-emerald-800"
                          : "bg-slate-200 text-slate-700"
                      }`}
                    >
                      {user.active ? "activo" : "inactivo"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {user.last_login_at ? new Date(user.last_login_at).toLocaleString() : "nunca"}
                  </td>
                  <td className="px-4 py-3">
                    <button
                      className="rounded-md border border-border px-3 py-1.5 text-xs font-medium"
                      aria-label={`${user.active ? "Desactivar" : "Activar"} ${user.username}`}
                      disabled={update.isPending}
                      onClick={() =>
                        update.mutate({
                          user,
                          payload: { active: !user.active },
                        })
                      }
                    >
                      {user.active ? "Desactivar" : "Activar"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
