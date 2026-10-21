// One icon vocabulary across device cards. Prefer MIoT category over model guesses.
Object.assign(icons,{
 device:'<rect x="4" y="3" width="16" height="18" rx="4"/><path d="M9 7h6M10 17h4"/>',
 speaker:'<rect x="6" y="3" width="12" height="18" rx="4"/><circle cx="12" cy="14" r="3"/><path d="M10 7h4"/>',
 clock:'<rect x="2" y="5" width="20" height="14" rx="4"/><circle cx="12" cy="12" r="4"/><path d="M12 9v3l2 1M6 21h12"/>',
 camera:'<rect x="3" y="4" width="18" height="13" rx="4"/><circle cx="12" cy="10" r="3"/><path d="M8 21h8M12 17v4"/>',
 washer:'<rect x="4" y="2" width="16" height="20" rx="3"/><circle cx="12" cy="14" r="5"/><path d="M7 6h3M16 6h1"/>',
 purifier:'<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M9 6h6M9 12h6M9 15h6M9 18h6"/><circle cx="12" cy="9" r=".6"/>',
 humidifier:'<path d="M5 12h14v7a3 3 0 0 1-3 3H8a3 3 0 0 1-3-3ZM8 9c-3-3 3-3 0-6M12 9c-3-3 3-3 0-6M16 9c-3-3 3-3 0-6"/><path d="M10 17h4"/>',
 kettle:'<path d="M6 8h11v10a3 3 0 0 1-3 3H9a3 3 0 0 1-3-3ZM9 5h5M11 2v3M17 10h2a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-2M6 10 3 8v6l3 2M9 12h5"/>',
 fish:'<rect x="2" y="5" width="20" height="15" rx="2"/><path d="M2 9c3-2 5 2 8 0s5 2 8 0 3 0 4 0M6 20v2M18 20v2M7 14c3-4 7-3 9 0-2 3-6 4-9 0Zm0 0-3-2v4l3-2M17 16v-4"/>',
 mosquito:'<path d="M7 5h10l2 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2ZM9 2h6M9 9h6M9 12h6M9 15h6"/><circle cx="12" cy="18" r=".6"/>',
 toothbrush:'<path d="M10 9h4v11a2 2 0 0 1-4 0ZM10 9V3a2 2 0 0 1 4 0v6M10 4h4M10 6h4M10 8h4M12 13v2"/>',
 router:'<rect x="3" y="13" width="18" height="7" rx="2"/><path d="M5 13V4M19 13V4M8 17h1M12 17h1M8 7a6 6 0 0 1 8 0M10 10a3 3 0 0 1 4 0"/>',
 sensor:'<rect x="4" y="3" width="16" height="18" rx="5"/><path d="M9 7v6a3 3 0 1 0 4 3c0-1-.5-2-2-3V7M14 7h2M14 10h2"/>',
 occupancy:'<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="9" r="2"/><path d="M8 17v-2a4 4 0 0 1 8 0v2M5 7v3M19 7v3"/>',
 strip:'<rect x="6" y="3" width="12" height="18" rx="3"/><path d="M12 3V1M9 7v2M15 7v2M12 10v1M9 14v2M15 14v2M12 17v1"/>',
 pump:'<circle cx="12" cy="13" r="6"/><path d="M6 13H2V8h4M18 13h4v5h-4M8 21h8M12 7V3M10 3h4M10 11l4 4M14 11l-4 4"/>',
 floorlamp:'<path d="M9 3h6l4 7H5ZM12 10v11M8 21h8M16 11v4"/>',
 nightlight:'<path d="M6 14a6 6 0 1 1 12 0v4H6ZM8 21h8M12 2V1M3 7 1 6M21 7l2-1"/><path d="M9 14a3 3 0 0 1 6 0"/>',
 remote:'<rect x="7" y="2" width="10" height="20" rx="4"/><circle cx="12" cy="8" r="2"/><path d="M10 14h4M10 17h4M10 20h4"/>'
});
window.deviceIconType=function(d){
 const model=d.model||'',name=d.name||'',category=d.spec_type?.split(':')[3];
 if(category==='outlet'&&/水泵/.test(name))return 'pump';
 if(category==='light'&&/落地灯/.test(name))return 'floorlamp';
 if(category==='light'&&/夜灯/.test(name))return 'nightlight';
 if(category==='speaker'&&(/lx04/.test(model)||/clock|时钟|闹钟/i.test(name)))return 'clock';
 if(category==='outlet'&&/cp5|排插|插排/.test(model+' '+name))return 'strip';
 const categories={'light':'light','air-conditioner':'air','television':'tv','speaker':'speaker','camera':'camera','washer':'washer','air-purifier':'purifier','humidifier':'humidifier','kettle':'kettle','fish-tank':'fish','mosquito-dispeller':'mosquito','toothbrush':'toothbrush','router':'router','temperature-humidity-sensor':'sensor','occupancy-sensor':'occupancy','outlet':'plug','fan':'fan'};
 if(categories[category])return categories[category];
 if(model.startsWith('miir.remote'))return /风扇/.test(name)?'fan':'remote';
 const models=[[/fishbowl/,'fish'],[/humidifier/,'humidifier'],[/airp\./,'purifier'],[/kettle/,'kettle'],[/mosq\./,'mosquito'],[/toothbrush/,'toothbrush'],[/router/,'router'],[/washer/,'washer'],[/sensor_occupy/,'occupancy'],[/sensor/,'sensor'],[/wifispeaker/,'speaker'],[/camera/,'camera'],[/airc|acpartner/,'air'],[/light/,'light'],[/fan/,'fan'],[/\.tv\./,'tv'],[/plug/,'plug']];
 return models.find(([pattern])=>pattern.test(model))?.[1]||'device';
};
