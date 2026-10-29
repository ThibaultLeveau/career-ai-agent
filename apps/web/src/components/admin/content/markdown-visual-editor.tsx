"use client";

import { useCallback, useRef, useState } from "react";
import {
  BlockTypeSelect,
  BoldItalicUnderlineToggles,
  CodeToggle,
  CreateLink,
  InsertCodeBlock,
  InsertTable,
  ListsToggle,
  MDXEditor,
  type MDXEditorMethods,
  StrikeThroughSupSubToggles,
  UndoRedo,
  codeBlockPlugin,
  codeMirrorPlugin,
  headingsPlugin,
  linkDialogPlugin,
  linkPlugin,
  listsPlugin,
  markdownShortcutPlugin,
  quotePlugin,
  tablePlugin,
  thematicBreakPlugin,
  toolbarPlugin,
} from "@mdxeditor/editor";
import "@mdxeditor/editor/style.css";

export default function MarkdownVisualEditor({
  value,
  label,
  onChange,
  disabled,
  onError,
}: {
  value: string;
  label: string;
  onChange: (value: string) => void;
  disabled: boolean;
  onError: () => void;
}) {
  const [initial] = useState(value);
  const initialized = useRef(false);
  const initialize = useCallback((editor: MDXEditorMethods | null) => {
    // The initial prop is trimmed by MDXEditor; its setter preserves indentation.
    if (editor && !initialized.current) {
      initialized.current = true;
      editor.setMarkdown(initial);
    }
  }, [initial]);
  const [container, setContainer] = useState<HTMLDivElement | null>(null);
  return (
    <div ref={setContainer} className="markdown-visual" aria-label={`${label} visual editor`}>
      {container && (
        <MDXEditor
          ref={initialize}
          markdown=""
          trim={false}
          suppressHtmlProcessing
          readOnly={disabled}
          overlayContainer={container.closest<HTMLElement>(".admin") ?? container}
          contentEditableClassName="markdown-prose"
          onChange={(markdown, initialNormalize) => {
            // Mounting an editor must not rewrite a saved or manually entered source.
            if (!initialNormalize) onChange(markdown);
          }}
          onError={onError}
          plugins={[
            headingsPlugin(),
            listsPlugin(),
            quotePlugin(),
            linkPlugin(),
            linkDialogPlugin(),
            thematicBreakPlugin(),
            tablePlugin(),
            codeBlockPlugin({ defaultCodeBlockLanguage: "txt" }),
            codeMirrorPlugin({ codeBlockLanguages: { txt: "Text", js: "JavaScript", ts: "TypeScript", py: "Python", sql: "SQL" } }),
            markdownShortcutPlugin(),
            toolbarPlugin({
              toolbarContents: () => <>
                <UndoRedo />
                <BlockTypeSelect />
                <BoldItalicUnderlineToggles options={["Bold", "Italic"]} />
                <StrikeThroughSupSubToggles options={["Strikethrough"]} />
                <CodeToggle />
                <ListsToggle />
                <CreateLink />
                <InsertTable />
                <InsertCodeBlock />
              </>,
            }),
          ]}
        />
      )}
    </div>
  );
}
