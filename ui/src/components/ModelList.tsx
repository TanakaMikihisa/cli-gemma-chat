import React from "react";
import { Box, Text } from "ink";
import { theme } from "../theme.js";
import type { ModelStatus } from "../types.js";

interface ModelListProps {
  models: ModelStatus[];
}

const statusIcon: Record<ModelStatus["status"], { icon: string; color: string }> = {
  local: { icon: theme.symbols.dot, color: theme.colors.success },
  cached: { icon: theme.symbols.dot, color: theme.colors.success },
  not_found: { icon: theme.symbols.dotEmpty, color: theme.colors.dim },
};

const statusLabel: Record<ModelStatus["status"], string> = {
  local: "local",
  cached: "cached",
  not_found: "not downloaded",
};

export const ModelList: React.FC<ModelListProps> = ({ models }) => {
  if (models.length === 0) return null;

  return (
    <Box flexDirection="column" marginBottom={1}>
      <Text dimColor>Models:</Text>
      {models.map((m, i) => {
        const st = statusIcon[m.status];
        return (
          <Box key={i} paddingLeft={2}>
            <Text color={st.color}>{st.icon}</Text>
            <Text> {m.name} </Text>
            {m.adapter && (
              <Text dimColor> with {m.adapter_name || "アダプタ"} </Text>
            )}
            <Text dimColor>({m.kind})</Text>
            <Text dimColor> [{statusLabel[m.status]}]</Text>
            {m.selected && (
              <Text color={theme.colors.warning}> ◀ loading</Text>
            )}
          </Box>
        );
      })}
    </Box>
  );
};
