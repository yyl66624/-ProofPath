/**
 * App 外壳 — 四步向导布局
 */
import { useApp } from "@/store/AppContext";
import { StepIndicator } from "@/components/StepIndicator";
import { DemoBanner } from "@/components/DemoBanner";
import { UploadStep } from "@/pages/UploadStep";
import { ProfileStep } from "@/pages/ProfileStep";
import { AnalysisStep } from "@/pages/AnalysisStep";
import { EvidenceStep } from "@/pages/EvidenceStep";
import type { WizardStep } from "@/types";
import { FileSearch } from "lucide-react";
import { setDemoMode } from "@/api/client";

const STEP_COMPONENTS: Record<WizardStep, React.FC> = {
  upload: UploadStep,
  profile: ProfileStep,
  analysis: AnalysisStep,
  evidence: EvidenceStep,
};

export default function App() {
  const { state, goToStep, dispatch } = useApp();
  const StepPage = STEP_COMPONENTS[state.currentStep];

  const toggleMode = (enabled: boolean) => {
    setDemoMode(enabled);
    dispatch({ type: "SET_DEMO_MODE", enabled });
  };

  return (
    <div className="min-h-screen flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-40">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <FileSearch className="w-6 h-6 text-brand-600" aria-hidden="true" />
            <h1 className="text-lg font-bold text-gray-900 tracking-tight">
              循据 <span className="text-brand-600">ProofPath</span>
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {/* 模式切换 */}
            <div
              role="group"
              aria-label="数据源切换"
              className="inline-flex rounded-full border border-gray-200 bg-gray-50 p-0.5 text-xs"
            >
              <button
                type="button"
                onClick={() => toggleMode(true)}
                aria-pressed={state.demoMode}
                className={`px-3 py-1 rounded-full transition-colors ${
                  state.demoMode
                    ? "bg-amber-500 text-white shadow-sm"
                    : "text-gray-600 hover:text-gray-900"
                }`}
              >
                演示样例
              </button>
              <button
                type="button"
                onClick={() => toggleMode(false)}
                aria-pressed={!state.demoMode}
                className={`px-3 py-1 rounded-full transition-colors ${
                  !state.demoMode
                    ? "bg-brand-600 text-white shadow-sm"
                    : "text-gray-600 hover:text-gray-900"
                }`}
              >
                真实接口
              </button>
            </div>
            <span className="text-xs text-gray-400">v0.1.0</span>
          </div>
        </div>
      </header>

      {/* 步骤指示器 */}
      <div className="bg-white border-b border-gray-100">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-4">
          <StepIndicator current={state.currentStep} onStepClick={goToStep} />
        </div>
      </div>

      {/* 主内容 */}
      <main className="flex-1 px-4 sm:px-6 py-6 sm:py-8">
        {/* 演示数据横幅 */}
        <div className="max-w-6xl mx-auto mb-4">
          <DemoBanner visible={state.demoMode} />
        </div>

        {/* 步骤页面 */}
        <StepPage />
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-white">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
          <p className="text-xs text-gray-400">
            本结果不是最终资格认定，请以受理窗口的答复为准。
          </p>
          <p className="text-xs text-gray-400">
            循据 ProofPath · 证据可核验的政策助手
          </p>
        </div>
      </footer>
    </div>
  );
}
