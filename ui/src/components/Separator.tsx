import React from "react";
import { Text } from "ink";
import { theme } from "../theme.js";
import { getTerminalWidth } from "../utils.js";

interface SeparatorProps {
  width?: number;
  char?: string;
}

export const Separator: React.FC<SeparatorProps> = ({
  width,
  char = theme.symbols.separator,
}) => {
  const w = width ?? getTerminalWidth();
  return <Text dimColor>{char.repeat(w)}</Text>;
};
