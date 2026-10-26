import { useState } from "react";
import { ModelChoice } from "../types/project";
import { Button } from "./ui/Button";
export function ModelSettings({
  initial,
  models,
  onSave,
  onReset,
  busy = false,
}: {
  initial: ModelChoice;
  models: Record<string, string[]>;
  onSave: (v: ModelChoice) => void;
  onReset?: () => void;
  busy?: boolean;
}) {
  const [value, setValue] = useState(initial);
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(value);
      }}
    >
      <div className="grid md:grid-cols-2 gap-4">
        <label className="text-sm space-y-2">
          <span>مصدر النموذج المدير</span>
          <select
            aria-label="مصدر النموذج المدير"
            className="glass-input"
            value={value.provider}
            onChange={(e) =>
              setValue({
                ...value,
                provider: e.target.value as ModelChoice["provider"],
                model: "",
              })
            }
          >
            <option value="groq">Groq</option>
            <option value="openrouter">OpenRouter</option>
          </select>
        </label>
        <label className="text-sm space-y-2">
          <span>النموذج المدير</span>
          <input
            dir="ltr"
            required
            list="director-models"
            className="glass-input"
            value={value.model}
            onChange={(e) => setValue({ ...value, model: e.target.value })}
            placeholder="معرّف النموذج لدى المزود"
            maxLength={200}
            pattern="\S+"
          />
          <datalist id="director-models">
            {models[value.provider]?.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </label>
        <label className="text-sm space-y-2">
          <span>درجة الإبداع</span>
          <input
            className="glass-input"
            type="number"
            min={0}
            max={1}
            step={0.1}
            value={value.temperature}
            required
            onChange={(e) =>
              setValue({ ...value, temperature: Number(e.target.value) })
            }
          />
        </label>
        <label className="text-sm space-y-2">
          <span>الحد الأقصى لطول الرد (Tokens)</span>
          <input
            className="glass-input"
            type="number"
            min={128}
            max={16384}
            value={value.max_tokens}
            required
            onChange={(e) =>
              setValue({ ...value, max_tokens: Number(e.target.value) })
            }
          />
        </label>
      </div>
      <p className="text-xs muted leading-6">
        يمكنك كتابة معرّف نموذج آخر يدعمه مزودك. يجب إعداد مفتاح المزود على
        الخادم.
        اختيار نموذج خاص هنا يجعله مسؤولًا أيضًا عن الإجابات المباشرة؛ الإعدادات الافتراضية تستخدم دور الاستجابة السريعة.
      </p>
      <div className="flex flex-wrap gap-3">
        <Button type="submit" isLoading={busy}>
          حفظ الإعدادات
        </Button>
        {onReset && (
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={onReset}
          >
            استخدام الإعدادات الافتراضية
          </Button>
        )}
      </div>
    </form>
  );
}
