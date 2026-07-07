"use client";

// FAQボット（/faq）LINE風チャットUI。推しアイコンが回答者。
// 初回メッセージ→質問チップ（GET /api/faq/topics）＋自由入力→POST /api/faq/ask
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import ScreenFrame from "@/components/ScreenFrame";
import IdolImage from "@/components/IdolImage";
import { useToast } from "@/components/Toast";
import { api } from "@/lib/api";
import { getStoredUser } from "@/lib/session";
import type { FaqTopic, User } from "@/lib/types";
import { FALLBACK_IDOLS } from "@/lib/idols";

interface Msg {
  id: number;
  role: "bot" | "user";
  text: string;
}

let msgSeq = 1;

export default function FaqPage() {
  const router = useRouter();
  const { show } = useToast();

  const [user, setUser] = useState<User | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [topics, setTopics] = useState<FaqTopic[]>([]);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 推しのテーマカラー
  const idol = user
    ? FALLBACK_IDOLS.find((i) => i.id === user.idol_id)
    : undefined;
  const theme = idol?.theme_color ?? "#ff87b2";

  useEffect(() => {
    const u = getStoredUser();
    if (!u) {
      router.replace("/");
      return;
    }
    setUser(u);
    // 初回メッセージ
    setMessages([
      {
        id: msgSeq++,
        role: "bot",
        text: `${u.nickname}、なにか気になることある？ 送り方でもポイントでも、なんでも聞いてね♪`,
      },
    ]);
    // 質問チップ取得
    api
      .getFaqTopics()
      .then(setTopics)
      .catch(() => {
        // 取得失敗時は既定のチップを表示
        setTopics([
          { id: "t1", category: "送付", question: "送付方法は？" },
          { id: "t2", category: "ポイント", question: "ポイントはいつもらえる？" },
          { id: "t3", category: "安全", question: "データ消去は安全？" },
        ]);
      });
  }, [router]);

  // 新規メッセージで一番下へスクロール
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || asking) return;
    setInput("");
    setMessages((prev) => [
      ...prev,
      { id: msgSeq++, role: "user", text: q },
    ]);
    setAsking(true);
    try {
      const res = await api.askFaq(q);
      setMessages((prev) => [
        ...prev,
        { id: msgSeq++, role: "bot", text: res.answer },
      ]);
    } catch {
      show("回答を取得できませんでした");
      setMessages((prev) => [
        ...prev,
        {
          id: msgSeq++,
          role: "bot",
          text: "ごめんね、うまく答えられなかったみたい…もう一度きいてくれる？",
        },
      ]);
    } finally {
      setAsking(false);
    }
  };

  return (
    <ScreenFrame
      bgClassName="bg-gradient-to-b from-[#fff2f8] to-[#eef1ff]"
      noPadding
    >
      {/* ヘッダー */}
      <header className="relative flex items-center gap-3 border-b border-[var(--pink-100)] bg-white/80 px-4 py-3 backdrop-blur">
        <button
          onClick={() => router.push("/home")}
          className="text-sm font-bold text-[var(--ink-soft)]"
        >
          ←
        </button>
        {user && (
          <IdolImage
            idolId={user.idol_id}
            name={idol?.name}
            size={36}
            variant="face"
          />
        )}
        <div className="leading-tight">
          <p className="text-sm font-extrabold text-[var(--ink)]">
            {idol?.name ?? "推し"}に相談
          </p>
          <p className="text-[10px] text-[var(--ink-soft)]">FAQボット</p>
        </div>
      </header>

      {/* メッセージ */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
        <div className="flex flex-col gap-3">
          {messages.map((m) =>
            m.role === "bot" ? (
              <div key={m.id} className="flex items-end gap-2">
                {user && (
                  <IdolImage
                    idolId={user.idol_id}
                    name={idol?.name}
                    size={32}
                    variant="face"
                  />
                )}
                <div
                  className="max-w-[75%] rounded-2xl rounded-bl-sm bg-white px-4 py-2.5 text-sm text-[var(--ink)] shadow-sm"
                  style={{ borderLeft: `3px solid ${theme}` }}
                >
                  {m.text}
                </div>
              </div>
            ) : (
              <div key={m.id} className="flex justify-end">
                <div
                  className="max-w-[75%] rounded-2xl rounded-br-sm px-4 py-2.5 text-sm text-white shadow-sm"
                  style={{ background: theme }}
                >
                  {m.text}
                </div>
              </div>
            )
          )}
          {asking && (
            <div className="flex items-end gap-2">
              {user && (
                <IdolImage
                  idolId={user.idol_id}
                  name={idol?.name}
                  size={32}
                  className="shrink-0 rounded-full"
                />
              )}
              <div className="rounded-2xl rounded-bl-sm bg-white px-4 py-3 text-sm shadow-sm">
                <span className="animate-twinkle">･･･</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 質問チップ（常設） */}
      {topics.length > 0 && (
        <div className="flex gap-2 overflow-x-auto border-t border-[var(--pink-100)] bg-white/60 px-4 py-2">
          {topics.map((t) => (
            <button
              key={t.id}
              onClick={() => ask(t.question)}
              disabled={asking}
              className="shrink-0 rounded-full border-2 px-3 py-1.5 text-xs font-bold disabled:opacity-50"
              style={{ borderColor: theme, color: theme }}
            >
              {t.question}
            </button>
          ))}
        </div>
      )}

      {/* 入力欄 */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask(input);
        }}
        className="flex items-center gap-2 border-t border-[var(--pink-100)] bg-white px-3 py-2.5"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="メッセージを入力…"
          className="flex-1 rounded-full border-2 border-[var(--pink-100)] bg-[var(--pink-50)] px-4 py-2.5 text-sm outline-none focus:border-[var(--pink-300)]"
        />
        <button
          type="submit"
          disabled={asking || !input.trim()}
          className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-white shadow disabled:opacity-40"
          style={{ background: theme }}
          aria-label="送信"
        >
          ➤
        </button>
      </form>
    </ScreenFrame>
  );
}
