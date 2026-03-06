import React, { useState, useCallback } from "react";
import { Box, Text, useInput } from "ink";
import { theme } from "../theme.js";
import { getTerminalWidth } from "../utils.js";

interface InputBoxProps {
  onSubmit: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export const InputBox: React.FC<InputBoxProps> = ({
  onSubmit,
  disabled = false,
  placeholder = "",
}) => {
  const [value, setValue] = useState("");
  const [cursorOffset, setCursorOffset] = useState(0);

  const width = getTerminalWidth();

  const handleSubmit = useCallback(() => {
    const trimmed = value.trim();
    if (trimmed) {
      onSubmit(trimmed);
      setValue("");
      setCursorOffset(0);
    }
  }, [value, onSubmit]);

  useInput(
    (input, key) => {
      if (disabled) return;

      if (key.return) {
        handleSubmit();
        return;
      }

      if (key.backspace || key.delete) {
        if (value.length > 0) {
          setValue((v) => v.slice(0, -1));
          setCursorOffset(0);
        }
        return;
      }

      if (key.ctrl && input === "c") {
        process.exit(0);
      }

      if (key.ctrl && input === "u") {
        setValue("");
        setCursorOffset(0);
        return;
      }

      if (!key.ctrl && !key.meta && input) {
        setValue((v) => v + input);
        setCursorOffset(0);
      }
    },
    { isActive: !disabled }
  );

  const borderChar = theme.symbols.separator;
  const borderLine = borderChar.repeat(width);

  const showPlaceholder = !value && placeholder;

  return (
    <Box flexDirection="column">
      <Text dimColor>{borderLine}</Text>
      <Box>
        <Text dimColor> {theme.symbols.chevron}</Text>
        <Text>{"  "}</Text>
        {showPlaceholder ? (
          <Text dimColor>{placeholder}</Text>
        ) : (
          <>
            <Text>{value}</Text>
            {!disabled && <Text color={theme.colors.primary}>▎</Text>}
          </>
        )}
      </Box>
      <Text dimColor>{borderLine}</Text>
    </Box>
  );
};
