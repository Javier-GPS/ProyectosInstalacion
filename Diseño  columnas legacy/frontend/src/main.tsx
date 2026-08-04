import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./auth/AuthContext";
import { ActiveProjectProvider } from "./projects/ActiveProjectContext";
import { DecisionPanelProvider } from "./layout/DecisionPanelContext";
import { AppRoutes } from "./routes";
import "./styles/theme.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <ActiveProjectProvider>
            <DecisionPanelProvider>
              <AppRoutes />
            </DecisionPanelProvider>
          </ActiveProjectProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
