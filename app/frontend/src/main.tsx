import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import "./index.css";
import App from "./App";
import HomePage from "./pages/HomePage";
import HotIssuesPage from "./pages/HotIssuesPage";
import SignalsPage from "./pages/SignalsPage";
import DeepDivePage from "./pages/DeepDivePage";

const router = createBrowserRouter([
  {
    path: "/",
    element: <App />,
    children: [
      { index: true, element: <HomePage /> },
      { path: "hot-issues", element: <HotIssuesPage /> },
      { path: "signals", element: <SignalsPage /> },
      { path: "deep-dive", element: <DeepDivePage /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
