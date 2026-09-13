/**
 * 全局应用状态 — 向导流程控制
 *
 * 使用 React Context 管理四步向导的状态流转，
 * 包括文档信息、用户资料、分析结果和当前步骤。
 */
import {
  createContext,
  useContext,
  useReducer,
  type ReactNode,
  useCallback,
} from "react";
import type {
  WizardStep,
  DocumentInfo,
  UserProfileField,
  AnalysisResult,
  ActionPlanItem,
} from "@/types";

/* ────────── 状态定义 ────────── */

interface AppState {
  /** 当前步骤 */
  currentStep: WizardStep;
  /** 是否演示模式 */
  demoMode: boolean;
  /** 文件上传 */
  document: DocumentInfo | null;
  question: string;
  /** 用户资料 */
  profileFields: UserProfileField[];
  profileValues: Record<string, string>;
  /** 分析结果 */
  analysisResult: AnalysisResult | null;
  /** 操作计划（P10） */
  actionPlan: ActionPlanItem[];
  /** 全局加载状态 */
  loading: boolean;
  /** 全局错误 */
  error: string | null;
}

const initialState: AppState = {
  currentStep: "upload",
  demoMode: true,
  document: null,
  question: "",
  profileFields: [],
  profileValues: {},
  analysisResult: null,
  actionPlan: [],
  loading: false,
  error: null,
};

/* ────────── 动作定义 ────────── */

type AppAction =
  | { type: "SET_STEP"; step: WizardStep }
  | { type: "SET_DEMO_MODE"; enabled: boolean }
  | { type: "SET_DOCUMENT"; document: DocumentInfo; question: string }
  | { type: "SET_PROFILE_FIELDS"; fields: UserProfileField[] }
  | { type: "UPDATE_PROFILE_VALUE"; fieldName: string; value: string }
  | { type: "SET_PROFILE_ERRORS"; errors: Record<string, string> }
  | { type: "SET_ANALYSIS_RESULT"; result: AnalysisResult }
  | { type: "SET_ACTION_PLAN"; plan: ActionPlanItem[] }
  | { type: "SET_LOADING"; loading: boolean }
  | { type: "SET_ERROR"; error: string | null }
  | { type: "RESET" };

/* ────────── Reducer ────────── */

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "SET_STEP":
      return { ...state, currentStep: action.step, error: null };

    case "SET_DEMO_MODE":
      return { ...state, demoMode: action.enabled };

    case "SET_DOCUMENT":
      return {
        ...state,
        document: action.document,
        question: action.question,
        error: null,
      };

    case "SET_PROFILE_FIELDS":
      return {
        ...state,
        profileFields: action.fields,
        profileValues: Object.fromEntries(
          action.fields.map((f) => [f.field_name, f.value])
        ),
      };

    case "UPDATE_PROFILE_VALUE":
      return {
        ...state,
        profileValues: {
          ...state.profileValues,
          [action.fieldName]: action.value,
        },
        // 清除该字段的错误
        profileFields: state.profileFields.map((f) =>
          f.field_name === action.fieldName ? { ...f, error: undefined } : f
        ),
      };

    case "SET_PROFILE_ERRORS":
      return {
        ...state,
        profileFields: state.profileFields.map((f) =>
          action.errors[f.field_name]
            ? { ...f, error: action.errors[f.field_name] }
            : f
        ),
      };

    case "SET_ANALYSIS_RESULT":
      return { ...state, analysisResult: action.result, error: null };

    case "SET_ACTION_PLAN":
      return { ...state, actionPlan: action.plan };

    case "SET_LOADING":
      return { ...state, loading: action.loading };

    case "SET_ERROR":
      return { ...state, error: action.error, loading: false };

    case "RESET":
      return { ...initialState, demoMode: state.demoMode };

    default:
      return state;
  }
}

/* ────────── Context ────────── */

interface AppContextType {
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
  goToStep: (step: WizardStep) => void;
  goBack: () => void;
  canGoBack: boolean;
}

const AppContext = createContext<AppContextType | null>(null);

const STEP_ORDER: WizardStep[] = ["upload", "profile", "analysis", "evidence"];

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  const goToStep = useCallback(
    (step: WizardStep) => dispatch({ type: "SET_STEP", step }),
    []
  );

  const goBack = useCallback(() => {
    const idx = STEP_ORDER.indexOf(state.currentStep);
    if (idx > 0) {
      dispatch({ type: "SET_STEP", step: STEP_ORDER[idx - 1] });
    }
  }, [state.currentStep]);

  const canGoBack = STEP_ORDER.indexOf(state.currentStep) > 0;

  return (
    <AppContext.Provider value={{ state, dispatch, goToStep, goBack, canGoBack }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp(): AppContextType {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}
