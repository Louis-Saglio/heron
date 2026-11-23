const ROUND = 100;

function round(value)
{
	return Math.round(value * ROUND) / ROUND;
}

function amount(value)
{
	return Number.isFinite(value) ? value : "Infinity";
}

function shape(ent)
{
	if (ent.get("Obstruction/Static"))
		return { "w": +ent.get("Obstruction/Static/@width"), "d": +ent.get("Obstruction/Static/@depth") };
	if (ent.get("Obstruction/Unit"))
		return { "r": +ent.get("Obstruction/Unit/@radius") };
	const radius = ent.obstructionRadius();
	return radius ? { "r": round(radius.max) } : undefined;
}

function place(ent)
{
	const position = ent.position();
	return { "id": ent.id(), "template": ent.templateName(), "owner": ent.owner(), "x": round(position[0]), "z": round(position[1]),
		"angle": round(ent.angle() || 0), "shape": shape(ent) };
}

function supply(ent)
{
	const type = ent.resourceSupplyType();
	return Object.assign(place(ent), {
		"type": type.generic + "." + type.specific,
		"amount": amount(ent.resourceSupplyAmount()),
		"max": amount(ent.resourceSupplyMax()),
		"places": ent.maxGatherers(),
		"gatherers": ent.resourceSupplyNumGatherers(),
		"diminishing": ent.get("ResourceSupply/DiminishingReturns") ? +ent.get("ResourceSupply/DiminishingReturns") : null
	});
}

function unit(ent)
{
	const order = ent.unitAIOrderData();
	return Object.assign(place(ent), {
		"classes": ent.classes(),
		"rates": ent.resourceGatherRates() || null,
		"capacities": ent.get("ResourceGatherer/Capacities") || null,
		"speed": ent.walkSpeed(),
		"build": ent.get("Builder/Rate") ? +ent.get("Builder/Rate") : null,
		"carrying": ent.resourceCarrying() || [],
		"state": ent.unitAIState(),
		"target": order && order.length && order[0].target !== undefined ? order[0].target : null
	});
}

function structure(ent)
{
	return Object.assign(place(ent), {
		"classes": ent.classes(),
		"dropsite": ent.resourceDropsiteTypes() || [],
		"foundation": ent.foundationProgress() === undefined ? null : ent.foundationProgress(),
		"queue": (ent.trainingQueue() || []).map(item => ({ "unit": item.unitTemplate || null, "tech": item.technologyTemplate || null, "count": item.count,
			"progress": round(item.progress || 0) })),
		"population": ent.getPopulationBonus() || 0
	});
}

function runs(data, mask)
{
	const out = [];
	let value = data[0] & mask;
	let count = 0;
	for (let i = 0; i < data.length; ++i)
	{
		const cell = data[i] & mask;
		if (cell === value)
		{
			++count;
			continue;
		}
		out.push(value, count);
		value = cell;
		count = 1;
	}
	out.push(value, count);
	return out;
}

function grid(map, mask)
{
	return { "width": map.width, "height": map.height, "cellSize": map.cellSize, "runs": runs(map.data, mask) };
}

export function snapshot(gameState, player)
{
	const own = [];
	const structures = [];
	const supplies = [];
	for (const ent of gameState.getEntities().values())
	{
		if (!ent.position())
			continue;
		if (ent.resourceSupplyType() && ent.resourceSupplyAmount())
			supplies.push(supply(ent));
		if (ent.owner() !== player)
			continue;
		if (ent.hasClass("Structure"))
			structures.push(structure(ent));
		else if (ent.hasClass("Unit"))
			own.push(unit(ent));
	}
	const shared = gameState.sharedScript;
	return {
		"time": gameState.getTimeElapsed(),
		"civ": gameState.getPlayerCiv(),
		"mapSize": shared.mapSize,
		"stock": gameState.getResources(),
		"population": gameState.getPopulation(),
		"populationLimit": gameState.getPopulationLimit(),
		"populationMax": gameState.getPopulationMax(),
		"researched": Array.from(gameState.playerData.researchedTechs),
		"barterPrices": gameState.getBarterPrices ? gameState.getBarterPrices() : null,
		"units": own,
		"structures": structures,
		"supplies": supplies,
		"territory": grid(shared.territoryMap, 0x1F),
		"passability": grid(shared.passabilityMap, shared.passabilityClasses["default-terrain-only"]),
		"passabilityMask": shared.passabilityClasses["default-terrain-only"]
	};
}
