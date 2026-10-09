/*
 * Hashtags em chips (da postagem da 006): Enter, vírgula ou espaço adicionam; Backspace no campo
 * vazio tira a última; colar "#a #b, c" adiciona todas, normalizadas e sem repetir.
 */
import { X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";
import { Badge } from "@/components/ui/badge";
import { HASHTAGS_MAX, parseHashtags } from "@/lib/postagem";

export function HashtagsInput({
  id,
  value,
  onChange,
  readOnly,
  invalid,
  describedBy,
}: {
  id: string;
  value: string[];
  onChange: (tags: string[]) => void;
  readOnly?: boolean;
  invalid?: boolean;
  describedBy?: string;
}) {
  const [input, setInput] = useState("");

  function add(text: string) {
    const tags = parseHashtags(text);
    if (tags.length === 0) return;
    onChange([...value, ...tags.filter((t) => !value.includes(t))].slice(0, HASHTAGS_MAX));
    setInput("");
  }

  function onKey(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" || e.key === "," || e.key === " ") {
      e.preventDefault();
      add(input);
    } else if (e.key === "Backspace" && !input && value.length > 0) {
      onChange(value.slice(0, -1));
    }
  }

  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border px-2 py-1.5 focus-within:ring-[3px] focus-within:ring-ring/50">
      <ul aria-label="Hashtags escolhidas" className="contents">
        {value.map((t) => (
          <li key={t}>
            <Badge variant="secondary" className="gap-1 pr-1">
              {t}
              {!readOnly && (
                <button type="button" aria-label={`Tirar ${t}`} className="rounded-full hover:bg-foreground/10" onClick={() => onChange(value.filter((x) => x !== t))}>
                  <X className="size-3" aria-hidden="true" />
                </button>
              )}
            </Badge>
          </li>
        ))}
      </ul>
      {!readOnly && value.length < HASHTAGS_MAX && (
        <input
          id={id}
          value={input}
          aria-invalid={invalid}
          aria-describedby={describedBy}
          placeholder={value.length === 0 ? "#achadinhos e Enter" : "+ hashtag"}
          className="min-w-24 flex-1 bg-transparent text-sm outline-none"
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          onBlur={() => add(input)}
          onPaste={(e) => {
            const text = e.clipboardData.getData("text");
            if (/[\s,]/.test(text)) {
              e.preventDefault();
              add(text);
            }
          }}
        />
      )}
    </div>
  );
}
