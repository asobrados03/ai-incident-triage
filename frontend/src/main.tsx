import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { AppLayout } from "@/app";
import { AuthProvider } from "@/auth";
import { ProtectedRoute } from "@/components/protected-route";
import { IncidentsPage } from "@/pages/incidents";
import { IncidentDetailPage } from "@/pages/incident-detail";
import { LoginPage } from "@/pages/login";
import { MetricsPage } from "@/pages/metrics";
import { NewIncidentPage } from "@/pages/new-incident";
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
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  </QueryClientProvider>,
);
