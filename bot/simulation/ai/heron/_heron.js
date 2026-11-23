import { BaseAI } from "simulation/ai/common-api/baseAI.js";
import { line } from "simulation/ai/heron/telemetry.js";
import { snapshot } from "simulation/ai/heron/world.js";

const DECISION_PERIOD = 8;
const DECISION_PHASE = 5;

export function HeronBot(settings)
{
	BaseAI.call(this, settings);
}

HeronBot.prototype = Object.create(BaseAI.prototype);

HeronBot.prototype.CustomInit = function(gameState)
{
	if (this.saved)
	{
		this.turn = this.saved.turn;
		this.exported = this.saved.exported;
		this.saved = undefined;
		return;
	}
	this.turn = 0;
	this.exported = false;
};

HeronBot.prototype.OnUpdate = function()
{
	if (this.gameState.playerData.state === "active" && (this.turn + this.player) % DECISION_PERIOD === DECISION_PHASE)
		this.decide();
	this.turn += 1;
};

HeronBot.prototype.decide = function()
{
	if (this.exported)
		return;
	line(this.player, "STATE", snapshot(this.gameState, this.player));
	this.exported = true;
};

HeronBot.prototype.Serialize = function()
{
	return { "turn": this.turn, "exported": this.exported };
};

HeronBot.prototype.Deserialize = function(data, sharedScript)
{
	BaseAI.prototype.Deserialize.call(this, data, sharedScript);
	this.saved = data;
};
