'use client';

import type { PayloadType } from '@agentigram/protocol';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import { describeEvent } from '../lib/demo-data';
import { useRoomStream } from '../lib/use-room-stream';

const filters: Array<{ label: string; types?: PayloadType[] }> = [
  { label: 'All' },
  { label: 'Changes', types: ['FILE_WRITE', 'API_DELTA', 'INTENT'] },
  { label: 'Coordination', types: ['COLLISION', 'MESSAGE', 'PROPOSAL', 'ACCEPT'] },
  { label: 'Checks', types: ['SPEC_MERGE_RESULT', 'CONTRACT_RESULT', 'RUN_VERIFIED'] },
];

export function RoomView({ teamId }: { teamId: string }) {
  const stream = useRoomStream(teamId);
  const events = stream.events;
  const displayedAgents = Object.values(stream.roomState.sessions)
    .filter((session) => session.status !== 'ended')
    .map((session) => ({
      id: session.sessionId,
      engineer: session.engineerId,
      role: session.role ?? session.sessionId,
      model: session.model,
      host: session.host,
      branch: session.branch,
      task: session.task ?? session.intent?.task ?? 'Awaiting task intent',
      status: session.status,
      lease: Object.values(stream.roomState.leases)
        .find((lease) => lease.sessionId === session.sessionId)
        ?.symbols[0]?.split('#')
        .at(-1)
        ?.split(':')[0],
    }));
  const latestCollision = [...events].reverse().find((event) => event.payload.type === 'COLLISION');
  const latestContractResult = [...events].reverse().find(
    (event) => event.payload.type === 'CONTRACT_RESULT' && event.payload.status === 'pass',
  );
  const latestCollisionSeq = latestCollision?.seq ?? -1;
  const latestPassSeq = latestContractResult?.seq ?? -1;
  const isPassed = latestPassSeq > latestCollisionSeq;
  const [filter, setFilter] = useState('All');
  const shownEvents = useMemo(() => {
    const selected = filters.find((item) => item.label === filter);
    const matching = selected?.types
      ? events.filter((event) => selected.types?.includes(event.payload.type))
      : events;
    return matching.slice(-8).reverse();
  }, [events, filter]);

  return (
    <div className="page room-page">
      <header className="page-header room-heading">
        <div>
          <p className="context-line">Room / {teamId}</p>
          <h1>One coordinator, three agents, one shared contract.</h1>
          <p>AgentSync monitors the seams between their work before integration fails.</p>
        </div>
        <div className="connection-state">
          <i className={stream.status === 'live' ? 'live' : ''}></i>
          <span>{stream.status === 'live' ? 'Live coordinator' : stream.status}</span>
        </div>
      </header>

      <section className={`signal-board ${isPassed ? 'passed' : ''}`} aria-labelledby="collision-title">
        <div className="signal-copy">
          <div className="signal-kicker">
            <span>{isPassed ? 'Contract Verified' : latestCollision ? 'Detected collision' : 'Collision monitor'}</span>
            {isPassed ? (
              <strong style={{ color: '#7bd0a3' }}>PASS · 100% verified</strong>
            ) : (
              latestCollision?.payload.type === 'COLLISION' && latestCollision.payload.confidence !== undefined && (
                <strong>{Math.round(latestCollision.payload.confidence * 100)}% confidence</strong>
              )
            )}
          </div>
          <h2 id="collision-title" style={isPassed ? { color: '#7bd0a3' } : undefined}>
            {isPassed
              ? 'CONTRACT VERIFIED: PASS'
              : latestCollision?.payload.type === 'COLLISION'
              ? `${latestCollision.payload.tier.replaceAll('_', ' ')} collision detected`
              : 'No collision reported by the live room.'}
          </h2>
          {isPassed ? (
            <>
              <p>Profile Agent updated user_id to UUID. Human approved in Nonilion. Contract compiled and verified.</p>
              <code style={{ color: '#7bd0a3' }}>src/user.ts#User.user_id:property → CONTRACT VERIFIED PASS</code>
            </>
          ) : latestCollision?.payload.type === 'COLLISION' ? (
            <>
              <p>{latestCollision.payload.detail}</p>
              {latestCollision.payload.symbols.map((symbol) => <code key={symbol}>{symbol}</code>)}
            </>
          ) : (
            <p>Collision information will appear here when the coordinator reports an event.</p>
          )}
        </div>
        <div
          className="signal-path"
          role="img"
          aria-label="Collision status from the live room"
        >
          {isPassed ? (
            <>
              <span className="role-avatar backend">a</span>
              <div><i></i><b style={{ color: '#7bd0a3', borderColor: 'rgba(78, 167, 122, 0.4)' }}>✓ Contract passed</b><i></i></div>
              <span className="role-avatar payments">p</span>
            </>
          ) : latestCollision?.payload.type === 'COLLISION' ? (
            <>
              <span className="role-avatar backend">{latestCollision.payload.writerSession[0]}</span>
              <div><i></i><b>{latestCollision.payload.affectedSessions.length} affected agents</b><i></i></div>
              <span className="role-avatar payments">{latestCollision.payload.affectedSessions[0]?.[0] ?? '?'}</span>
            </>
          ) : <span>Waiting for live collision events</span>}
        </div>
        <Link className="text-action" href={`/team/${teamId}/contracts`}>
          {isPassed ? 'View verified contract' : 'Review collision'}
        </Link>
      </section>

      <div className="room-grid">
        <section className="agents-panel" aria-labelledby="agents-title">
          <div className="section-heading">
            <h2 id="agents-title">Agents</h2>
            <span>{displayedAgents.filter((agent) => agent.status !== 'idle').length} working</span>
          </div>
          <div className="agent-list">
            {displayedAgents.map((agent) => (
              <article className="agent-row" key={agent.id}>
                <span className={`role-avatar ${agent.id}`}>{agent.role[0]}</span>
                <div className="agent-primary">
                  <strong>{agent.role}</strong>
                  <span>{agent.task}</span>
                </div>
                <div className="agent-model">
                  <strong>{agent.model}</strong>
                  <span>{agent.branch}</span>
                </div>
                <span className={`agent-state ${agent.status}`}>{agent.status}</span>
                {agent.lease && <code className="lease">{agent.lease}</code>}
              </article>
            ))}
            {displayedAgents.length === 0 && <p>No agents have connected to this room yet.</p>}
          </div>
        </section>

        <section className="feed-panel" aria-labelledby="feed-title">
          <div className="section-heading feed-heading">
            <div>
              <h2 id="feed-title">Live activity</h2>
              <span>seq {events.at(-1)?.seq ?? 0}</span>
            </div>
            <fieldset className="filter-row">
              <legend>Filter events</legend>
              {filters.map((item) => (
                <button
                  className={filter === item.label ? 'selected' : ''}
                  key={item.label}
                  onClick={() => setFilter(item.label)}
                  type="button"
                >
                  {item.label}
                </button>
              ))}
            </fieldset>
          </div>
          <ol className="event-list">
            {shownEvents.map((event) => (
              <li key={event.seq}>
                <time>
                  {new Date(event.ts).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })}
                </time>
                <span className={`event-dot event-${event.payload.type.toLowerCase()}`}></span>
                <p>
                  <strong>#{event.seq}</strong>
                  {describeEvent(event)}
                </p>
              </li>
            ))}
            {shownEvents.length === 0 && <li><p>No live events received yet.</p></li>}
          </ol>
        </section>
      </div>
    </div>
  );
}
