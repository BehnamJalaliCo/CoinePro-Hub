package com.coinepro.hq.designsystem

import androidx.compose.ui.unit.dp

/** One spacing scale for the whole app (4-point): gaps inside a row, between a card's parts, between sections. Hierarchy comes
 *  from space and surface, not from borders. */
object Space {
    val xxs = 4.dp
    val xs = 8.dp
    val sm = 12.dp
    val md = 16.dp
    val lg = 20.dp
    val xl = 24.dp
    val xxl = 32.dp
}

/** Corner radii: a card, a tile inside a card, a control (button, field), a small chip-like box. Pills are round. */
object Radius {
    val card = 16.dp
    val tile = 12.dp
    val control = 10.dp
    val small = 8.dp
}
