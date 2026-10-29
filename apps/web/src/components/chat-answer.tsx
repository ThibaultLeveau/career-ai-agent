import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function ChatAnswer({ text }: { text: string }) {
  return <Markdown
    remarkPlugins={[remarkGfm]}
    skipHtml
    disallowedElements={["img"]}
    urlTransform={(url) => {
      try {
        const parsed = new URL(url);
        return parsed.protocol === "https:" || parsed.protocol === "http:" ? url : "";
      } catch {
        return "";
      }
    }}
    components={{
      a: ({ href, children }) => href
        ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
        : <>{children}</>,
      table: ({ children }) => <div className="answer-table" tabIndex={0} role="region" aria-label="Answer table"><table>{children}</table></div>,
    }}
  >{text}</Markdown>;
}
