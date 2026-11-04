import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/app";
import { AuthProvider } from "@/auth";
import { ProtectedRoute } from "@/shared/components/protected-route";
import { IncidentsPage } from "@/features/incidents/pages/incidents";
import { IncidentDetailPage } from "@/features/incidents/pages/incident-detail";
import { LoginPage } from "@/pages/login";
import { MetricsPage } from "@/features/metrics/pages/metrics";
import { NewIncidentPage } from "@/features/incidents/pages/new-incident";
import { UsersPage } from "@/pages/users";
import "@/index.css";

const queryClient = new QueryClient();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={queryClient}>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route path="login" element={<LoginPage />} />
            <Route element={<ProtectedRoute />}>
              <Route index element={<IncidentsPage />} />
              <Route path="new" element={<NewIncidentPage />} />
              <Route path="incidents" element={<IncidentsPage />} />
              <Route path="incidents/:id" element={<IncidentDetailPage />} />
              <Route path="metrics" element={<MetricsPage />} />
              <Route path="users" element={<UsersPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </QueryClientProvider>,
);
