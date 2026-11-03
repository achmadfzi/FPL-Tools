import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell, useMode } from "@/components/app-shell";
import DashboardPage from "@/pages/dashboard";
import SquadPage from "@/pages/squad";
import PlayersPage from "@/pages/players";
import PerformancePage from "@/pages/performance";
import LabPage from "@/pages/lab";
import GlossaryPage from "@/pages/glossary";
import DetailPage from "@/pages/detail";
import CaptainPage from "@/pages/captain";
import HistoryPage from "@/pages/history";

export default function App() {
  const { mode, setMode } = useMode();
  const isBeginner = mode === "Pemula";

  return (
    <AppShell mode={mode} setMode={setMode}>
      <Routes>
        <Route path="/" element={<DashboardPage isBeginner={isBeginner} />} />
        <Route path="/squad" element={<SquadPage isBeginner={isBeginner} />} />
        <Route path="/players" element={<PlayersPage isBeginner={isBeginner} />} />
        <Route path="/performance" element={<PerformancePage isBeginner={isBeginner} />} />
        <Route path="/lab" element={<LabPage isBeginner={isBeginner} />} />
        <Route path="/glossary" element={<GlossaryPage />} />
        <Route path="/detail" element={<DetailPage isBeginner={isBeginner} />} />
        <Route path="/captain" element={<CaptainPage isBeginner={isBeginner} />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppShell>
  );
}
