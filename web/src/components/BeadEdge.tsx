import { BaseEdge, getBezierPath, type EdgeProps } from "@xyflow/react";

/** Bezier edge with a small bead travelling along the pipe while active.
 *  `reverse` makes the bead travel back up the pipe (agent → orchestrator). */
export function BeadEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  style,
  markerEnd,
  data,
}: EdgeProps) {
  const [path] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });
  const config = (data ?? {}) as {
    active?: boolean;
    color?: string;
    reverse?: boolean;
  };
  const color = config.color ?? "#38bdf8";
  const pathId = `bead-path-${id}`;

  return (
    <>
      <BaseEdge id={id} path={path} style={style} markerEnd={markerEnd} />
      {config.active && (
        <>
          <path id={pathId} d={path} fill="none" stroke="none" />
          <circle r={3.4} fill={color} style={{ filter: `drop-shadow(0 0 5px ${color})` }}>
            <animateMotion
              dur="1.6s"
              repeatCount="indefinite"
              rotate="auto"
              keyPoints={config.reverse ? "1;0" : undefined}
              keyTimes={config.reverse ? "0;1" : undefined}
            >
              <mpath href={`#${pathId}`} />
            </animateMotion>
          </circle>
        </>
      )}
    </>
  );
}
