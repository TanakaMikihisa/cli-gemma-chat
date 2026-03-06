import React from "react";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { Box, Text } from "ink";
import { theme } from "../theme.js";
import { getTerminalWidth } from "../utils.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const BANNER_FILE = resolve(__dirname, "..", "..", "..", "banner.txt");

function loadBannerArt(): string[] {
  try {
    const raw = readFileSync(BANNER_FILE, "utf-8");
    return raw
      .split("\n")
      .map((l) => l.trimEnd())
      .filter((l) => l.length > 0);
  } catch {
    return ["GEM CHAT"];
  }
}

interface BannerProps {
  modelName?: string;
}

export const Banner: React.FC<BannerProps> = ({ modelName }) => {
  const width = getTerminalWidth();
  const colors = theme.colors.banner;
  const bannerArt = loadBannerArt();

  return (
    <Box flexDirection="column" marginTop={1} marginBottom={1}>
      {bannerArt.map((line, lineIdx) => (
        <Text key={lineIdx} bold>
          {colorizeGradient(line, colors, width)}
        </Text>
      ))}
      <Box marginTop={1} flexDirection="column">
        {modelName && (
          <Text dimColor>  Model: {modelName}</Text>
        )}
        <Text dimColor>  {theme.symbols.arrow} Talk to me. Type quit or exit to end.</Text>
      </Box>
    </Box>
  );
};

function colorizeGradient(
  line: string,
  colors: readonly string[],
  _maxWidth: number
): React.ReactNode {
  if (!line) return null;
  const n = colors.length;
  const L = line.length;
  const segments: React.ReactNode[] = [];

  let currentColor = "";
  let currentChars = "";

  for (let i = 0; i < L; i++) {
    const idx = Math.min(Math.floor((i * n) / L), n - 1);
    const color = colors[idx]!;
    if (color !== currentColor) {
      if (currentChars) {
        segments.push(
          <Text key={segments.length} color={currentColor}>
            {currentChars}
          </Text>
        );
      }
      currentColor = color;
      currentChars = line[i]!;
    } else {
      currentChars += line[i];
    }
  }
  if (currentChars) {
    segments.push(
      <Text key={segments.length} color={currentColor}>
        {currentChars}
      </Text>
    );
  }

  return <>{segments}</>;
}
